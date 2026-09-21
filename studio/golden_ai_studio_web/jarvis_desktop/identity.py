"""Persistent, Gateway-issued identity for the native desktop shell."""
from __future__ import annotations

import asyncio
import base64
import ctypes
import json
import socket
import urllib.request
import uuid
from ctypes import wintypes

import aiohttp
from PySide6.QtCore import QSettings


PAIRING_CODE_URL = "https://127.0.0.1:8766/pairing/code"
PAIRING_CONFIRM_URL = "https://127.0.0.1:8766/pairing/confirm"
GATEWAY_WS_URL = "wss://127.0.0.1:8766/ws"


class DesktopIdentityError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_secret(secret: str) -> str:
    """Encrypt a secret for the current Windows user with DPAPI."""
    incoming, keepalive = _blob(secret.encode("utf-8"))
    outgoing = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(incoming), "Golden JARVIS Desktop", None, None, None,
            0, ctypes.byref(outgoing)):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(outgoing.pbData, outgoing.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)
        del keepalive


def unprotect_secret(value: str) -> str:
    encrypted = base64.b64decode(value.encode("ascii"), validate=True)
    incoming, keepalive = _blob(encrypted)
    outgoing = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(incoming), None, None, None, None, 0,
            ctypes.byref(outgoing)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)
        del keepalive


class DesktopCredentialStore:
    """Stores only DPAPI ciphertext and non-secret identity metadata."""

    def __init__(self, settings=None):
        self.settings = settings or QSettings("GoldenAI", "JarvisDesktop")

    def load_token(self):
        encrypted = self.settings.value("identity/device_token_dpapi", "")
        if not encrypted:
            return None
        try:
            return unprotect_secret(str(encrypted))
        except Exception:
            self.clear()
            return None

    def save(self, token, device_id):
        self.settings.setValue("identity/device_token_dpapi", protect_secret(token))
        self.settings.setValue("identity/device_id", device_id)
        self.settings.sync()

    def clear(self):
        self.settings.remove("identity/device_token_dpapi")
        self.settings.remove("identity/device_id")
        self.settings.sync()


class DesktopIdentityManager:
    def __init__(self, ssl_context, store=None, http_post=None, validator=None):
        self.ssl_context = ssl_context
        self.store = store or DesktopCredentialStore()
        self._http_post_override = http_post
        self._validator_override = validator

    def ensure_identity(self):
        token = self.store.load_token()
        if token and self._validate(token):
            print("[JARVIS-DESKTOP] Device identity: reused; auth=ok", flush=True)
            return token
        if token:
            self.store.clear()
            print("[JARVIS-DESKTOP] Device identity: rejected; repairing", flush=True)
        token, device_id = self._pair()
        if not self._validate(token):
            raise DesktopIdentityError("O Gateway recusou a identidade recém-pareada.")
        self.store.save(token, device_id)
        print("[JARVIS-DESKTOP] Device identity: paired; auth=ok", flush=True)
        return token

    def _post(self, url, payload):
        if self._http_post_override:
            return self._http_post_override(url, payload)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(
                request, timeout=5, context=self.ssl_context) as response:
            return json.loads(response.read().decode("utf-8"))

    def _pair(self):
        try:
            code_reply = self._post(PAIRING_CODE_URL, {})
            code = code_reply.get("code", "")
            if not code_reply.get("ok") or not code:
                raise DesktopIdentityError("O Gateway não iniciou o pairing local.")
            reply = self._post(PAIRING_CONFIRM_URL, {
                "code": code,
                "device_name": f"JARVIS Desktop - {socket.gethostname()}",
                "device_type": "desktop",
            })
        except DesktopIdentityError:
            raise
        except Exception as exc:
            raise DesktopIdentityError(
                f"Falha no pairing local ({type(exc).__name__}).") from exc
        token = reply.get("token", "")
        device_id = reply.get("device_id", "")
        if not reply.get("ok") or not token or not device_id:
            raise DesktopIdentityError("O Gateway não concluiu o pairing local.")
        return token, device_id

    def _validate(self, token):
        if self._validator_override:
            return bool(self._validator_override(token))
        try:
            return asyncio.run(self._validate_async(token))
        except Exception as exc:
            print("[JARVIS-DESKTOP] Device auth check failed: "
                  f"{type(exc).__name__}", flush=True)
            return False

    async def _validate_async(self, token):
        request_id = "desktop-auth-" + uuid.uuid4().hex
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                    GATEWAY_WS_URL, ssl=self.ssl_context, timeout=5) as ws:
                await ws.send_json({"version": 1, "id": request_id,
                                    "type": "auth", "payload": {"token": token}})
                message = await asyncio.wait_for(ws.receive(), timeout=5)
                if message.type != aiohttp.WSMsgType.TEXT:
                    return False
                reply = json.loads(message.data)
                return reply.get("type") == "auth_ok"

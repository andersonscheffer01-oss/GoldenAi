"""Ephemeral identity and narrowly scoped cooperative Core shutdown."""
from __future__ import annotations

import ipaddress
import os
import threading
import time
import uuid
from datetime import datetime, timezone

from .models import Risk, Tool


CORE_LIFECYCLE_CONTROL = "CORE_LIFECYCLE_CONTROL"
CORE_SHUTDOWN_PATH = "/core/shutdown"
_REQUEST_TTL_SECONDS = 30
_MAX_USED_REQUESTS = 4096
_DEVICE_TYPE_CAPABILITIES = {
    "desktop": frozenset({CORE_LIFECYCLE_CONTROL}),
}


def _process_identity(pid):
    """Return a process creation identity without POSIX-only liveness probes."""
    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        try:
            process = psutil.Process(int(pid))
            return {"pid": process.pid, "created_at": process.create_time()}
        except psutil.NoSuchProcess:
            return None
        except (psutil.AccessDenied, OSError, ValueError, TypeError):
            return {"pid": int(pid), "created_at": None}

    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
            return {"pid": int(pid), "created_at": None}
        except (OSError, ValueError, TypeError):
            return None

    import ctypes
    from ctypes import wintypes

    class FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(FileTime), ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime), ctypes.POINTER(FileTime),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, int(pid))
    if not handle:
        error = ctypes.get_last_error()
        return None if error in (87, 1168) else {"pid": int(pid), "created_at": None}
    try:
        created = FileTime()
        exited = FileTime()
        kernel = FileTime()
        user = FileTime()
        if not kernel32.GetProcessTimes(
                handle, ctypes.byref(created), ctypes.byref(exited),
                ctypes.byref(kernel), ctypes.byref(user)):
            return {"pid": int(pid), "created_at": None}
        ticks = (created.high << 32) | created.low
        return {"pid": int(pid), "created_at": ticks / 10_000_000 - 11_644_473_600}
    finally:
        kernel32.CloseHandle(handle)


class CoreLifecycle:
    def __init__(self, *, runtime_profile, auth_manager, security_manager,
                 audit_log, pid=None, parent_pid=None, runtime_instance_id=None,
                 started_at=None, market_live_available=False, clock=time.time):
        self.runtime_instance_id = str(runtime_instance_id or uuid.uuid4())
        self.pid = int(pid or os.getpid())
        self.parent_pid = int(os.getppid() if parent_pid is None else parent_pid)
        owner_identity = _process_identity(self.parent_pid) if self.parent_pid > 0 else None
        self._owner_created_at = (
            owner_identity.get("created_at") if owner_identity else None
        )
        self.runtime_profile = str(runtime_profile)
        self.started_at = started_at or datetime.now(timezone.utc).isoformat()
        self.market_live_available = bool(market_live_available)
        self.auth_manager = auth_manager
        self.security_manager = security_manager
        self.audit_log = audit_log
        self._clock = clock
        self._lock = threading.Lock()
        self._used_requests = {}
        self._state = "RUNNING"

    def snapshot(self):
        if self.parent_pid <= 0:
            owner_state = "DETACHED"
            current_owner = None
        else:
            current_owner = _process_identity(self.parent_pid)
            if current_owner is None:
                owner_state = "ORPHANED"
            elif (self._owner_created_at is not None and
                  current_owner.get("created_at") != self._owner_created_at):
                owner_state = "ORPHANED"
            elif current_owner.get("created_at") is None:
                owner_state = "UNKNOWN"
            elif os.getppid() == self.parent_pid:
                owner_state = "LAUNCHER_ATTACHED"
            else:
                owner_state = "LAUNCHER_ALIVE_NOT_PARENT"
        return {
            "runtime_instance_id": self.runtime_instance_id,
            "pid": self.pid,
            "started_at": self.started_at,
            "runtime_profile": self.runtime_profile,
            "lifecycle_state": self._state,
            "owner": {
                "type": "desktop_launcher",
                "launcher_pid": self.parent_pid,
                "launcher_created_at": self._owner_created_at,
                "relationship": "parent_at_start",
                "state": owner_state,
            },
            "capabilities": [
                "CORE_LIFECYCLE_CONTROL",
                *(["golden_market_live"] if self.market_live_available else []),
            ],
        }

    @staticmethod
    def _request_id(value):
        try:
            parsed = uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            return ""
        return str(parsed) if parsed.version == 4 else ""

    def _audit(self, *, status, request_id, source_ip, device_id="", reason=""):
        self.audit_log.add(
            task_id=request_id or "core-lifecycle",
            command="core_lifecycle_shutdown",
            tool="core_lifecycle_control",
            risk="HIGH",
            status=status,
            arguments={"runtime_instance_id": self.runtime_instance_id,
                       "device_id": device_id},
            result={"ok": status == "CORE_SHUTDOWN_ACCEPTED", "reason": reason},
            envelope={
                "request_id": request_id,
                "correlation_id": request_id,
                "surface": "core_lifecycle",
                "operation": "POST " + CORE_SHUTDOWN_PATH,
                "action": status,
                "target": self.runtime_instance_id,
                "tool": "core_lifecycle_control",
                "risk": "HIGH",
                "security_decision": "ALLOW" if status == "CORE_SHUTDOWN_ACCEPTED" else "DENY",
                "status": status,
                "error": reason,
                "runtime_profile": self.runtime_profile,
                "metadata": {"source_ip": str(source_ip)[:80], "device_id": device_id},
            },
        )

    def authorize_shutdown(self, payload, *, source_ip, authorization,
                           origin="", sec_fetch_site="", content_type=""):
        data = payload if isinstance(payload, dict) else {}
        request_id = self._request_id(data.get("request_id"))
        device_id = ""

        def deny(status, code, http_status=403):
            try:
                self._audit(status=status, request_id=request_id,
                            source_ip=source_ip, device_id=device_id, reason=code)
            except Exception:
                code = "AUDIT_UNAVAILABLE"
                http_status = 503
            return {"ok": False, "error": code, "_http_status": http_status}

        try:
            address = ipaddress.ip_address(str(source_ip).strip("[]"))
        except ValueError:
            return deny("CORE_SHUTDOWN_DENIED", "LOOPBACK_REQUIRED")
        if not address.is_loopback:
            return deny("CORE_SHUTDOWN_DENIED", "LOOPBACK_REQUIRED")
        if self.runtime_profile != "web-ai-safe":
            return deny("CORE_SHUTDOWN_DENIED", "RUNTIME_PROFILE_FORBIDDEN")
        if origin or sec_fetch_site:
            return deny("CORE_SHUTDOWN_DENIED", "BROWSER_CALL_FORBIDDEN")
        if str(content_type).split(";", 1)[0].strip().lower() != "application/json":
            return deny("CORE_SHUTDOWN_DENIED", "JSON_REQUIRED", 415)
        if not request_id:
            return deny("CORE_SHUTDOWN_DENIED", "REQUEST_ID_INVALID", 400)
        try:
            issued_at = float(data.get("issued_at"))
        except (TypeError, ValueError):
            return deny("CORE_SHUTDOWN_DENIED", "REQUEST_EXPIRED", 400)
        if abs(self._clock() - issued_at) > _REQUEST_TTL_SECONDS:
            return deny("CORE_SHUTDOWN_DENIED", "REQUEST_EXPIRED", 408)
        if data.get("runtime_instance_id") != self.runtime_instance_id:
            return deny("CORE_SHUTDOWN_DENIED", "RUNTIME_INSTANCE_MISMATCH", 409)

        raw = str(authorization or "")
        if not raw.startswith("Bearer ") or not raw[7:] or raw[7:].strip() != raw[7:]:
            return deny("CORE_SHUTDOWN_DENIED", "AUTH_REQUIRED", 401)
        token = raw[7:]
        try:
            auth_state = self.auth_manager.authenticate(
                token, source_ip=str(source_ip), update_device_last_seen=False)
            pairing = getattr(self.auth_manager, "_device_pairing", None)
            device = (pairing.verify_device_token(token, update_last_seen=False)
                      if pairing and auth_state.authenticated else None)
        except Exception:
            return deny("CORE_SHUTDOWN_DENIED", "AUTH_INVALID", 401)
        if not auth_state.authenticated or device is None:
            return deny("CORE_SHUTDOWN_DENIED", "DESKTOP_IDENTITY_REQUIRED", 401)
        device_id = str(device.device_id)
        device_type = str(device.device_type).casefold()
        explicit_capabilities = {
            name for name, enabled in (device.capabilities or {}).items() if enabled
        }
        explicit_capabilities.update(_DEVICE_TYPE_CAPABILITIES.get(device_type, ()))
        if CORE_LIFECYCLE_CONTROL not in explicit_capabilities:
            return deny("CORE_SHUTDOWN_DENIED", "LIFECYCLE_CAPABILITY_REQUIRED")

        tool = Tool(
            name="core_lifecycle_control",
            description="Cooperative shutdown of this Jarvis Core instance",
            handler=lambda **_: {"ok": True},
            risk=Risk.LOW,
            confirmation=False,
            llm_enabled=False,
            capability_name=CORE_LIFECYCLE_CONTROL,
        )
        security_context = {
            "request_id": request_id,
            "correlation_id": request_id,
            "task_id": request_id,
            "surface": "core_lifecycle",
            "operation": "POST " + CORE_SHUTDOWN_PATH,
            "target": self.runtime_instance_id,
            "runtime_profile": self.runtime_profile,
            "metadata": {"device_id": device_id, "source_ip": str(source_ip)},
        }
        try:
            decision = self.security_manager.decision(
                tool, risk=Risk.LOW,
                authorization_scope=CORE_LIFECYCLE_CONTROL,
                audit_context=security_context)
        except Exception:
            return deny("CORE_SHUTDOWN_DENIED", "SECURITY_OR_AUDIT_UNAVAILABLE", 503)
        if decision != "allow":
            return deny("CORE_SHUTDOWN_DENIED", "SECURITY_MANAGER_DENIED")

        now = self._clock()
        with self._lock:
            self._used_requests = {
                key: stamp for key, stamp in self._used_requests.items()
                if now - stamp <= _REQUEST_TTL_SECONDS
            }
            if request_id in self._used_requests:
                return deny("CORE_SHUTDOWN_DENIED", "REQUEST_REPLAYED", 409)
            if len(self._used_requests) >= _MAX_USED_REQUESTS:
                return deny("CORE_SHUTDOWN_DENIED", "REPLAY_GUARD_BUSY", 429)
            if self._state != "RUNNING":
                return deny("CORE_SHUTDOWN_DENIED", "SHUTDOWN_ALREADY_REQUESTED", 409)
            try:
                self._audit(status="CORE_SHUTDOWN_ACCEPTED", request_id=request_id,
                            source_ip=source_ip, device_id=device_id)
            except Exception:
                return {"ok": False, "error": "AUDIT_UNAVAILABLE", "_http_status": 503}
            self._used_requests[request_id] = now
            self._state = "SHUTDOWN_REQUESTED"
        return {"ok": True, "runtime_instance_id": self.runtime_instance_id,
                "pid": self.pid, "request_id": request_id,
                "lifecycle_state": self._state, "_http_status": 202}


def schedule_graceful_shutdown(server):
    """Ask the serving loop to exit from outside its request-handler thread."""
    def request():
        time.sleep(0.05)
        server.shutdown()

    threading.Thread(target=request, name="jarvis-core-shutdown",
                     daemon=True).start()


def server_is_serving(server):
    """Avoid BaseServer.shutdown before serve_forever has entered its loop."""
    stopped = getattr(server, "_BaseServer__is_shut_down", None)
    return stopped is None or not stopped.is_set()

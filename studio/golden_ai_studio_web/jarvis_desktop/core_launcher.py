"""Locate or launch the existing server_agent runtime exactly once."""
from __future__ import annotations

import json
import io
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .boot_diagnostics import boot_log
from .settings import studio_root, ui_url


HTTPS_HEALTH_URL = "https://127.0.0.1:8766/health"
HTTPS_UI_ORIGIN = "https://127.0.0.1:8765"
HTTPS_SHUTDOWN_URL = "https://127.0.0.1:8766/core/shutdown"


class CoreLaunchError(RuntimeError):
    pass


class CoreLauncher:
    def __init__(self, root=None, python_executable=None, popen=subprocess.Popen,
                 timeout=45.0, probe=None, ui_probe=None, host_provider=None,
                 runtime_profile=None, lifecycle_token=None,
                 required_capabilities=()):
        self.root = Path(root or studio_root()).resolve()
        self.python_executable = str(
            python_executable or self._default_python_executable())
        self._popen = popen
        self.timeout = float(timeout)
        self._probe_override = probe
        self._ui_probe_override = ui_probe
        self._host_provider = host_provider
        self.runtime_profile = str(runtime_profile).strip() if runtime_profile else None
        self.lifecycle_token = str(lifecycle_token or "")
        self.required_capabilities = frozenset(required_capabilities or ())
        self.process = None
        # A canonical Core may have been started by the launcher before this
        # Desktop shell was created. Keep its authenticated health snapshot so
        # the official exit command can close that adopted runtime too.
        self._adopted_health = None
        self.origin = None
        self._last_health = None
        self._shutdown_requested = False
        self._spawn_attempt_id = ""
        self._process_watch = None

    def _default_python_executable(self):
        if not getattr(sys, "frozen", False):
            return Path(sys.executable)

        configured = os.environ.get("GOLDEN_PYTHON", "").strip()
        candidates = ([Path(configured)] if configured else [])
        candidates.extend([
            self.root.parent.parent / ".venv" / "Scripts" / "python.exe",
            Path(sys.executable).with_name("python.exe"),
        ])
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise CoreLaunchError(
            "O Python do Golden não foi encontrado para iniciar o Core. "
            "Configure GOLDEN_PYTHON com o caminho do interpretador.")

    @property
    def owns_core(self):
        return self.process is not None

    def _ssl_context(self):
        ca_path = Path(r"C:\GoldenAI\certs\golden-local-ca.pem")
        if not ca_path.is_file():
            raise CoreLaunchError(
                "TLS está ativo, mas a CA local do Golden não foi encontrada.")
        context = ssl.create_default_context(cafile=str(ca_path))
        # Python 3.13 enables X509_STRICT by default. The current Golden CA is
        # trusted and cryptographically verified, but predates the mandatory
        # Authority Key Identifier check imposed by that compatibility flag.
        strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
        if strict:
            context.verify_flags &= ~strict
        return context

    def probe(self, health_url):
        print(f"[JARVIS-DESKTOP] Health probe: {health_url}", flush=True)
        if self._probe_override:
            healthy = bool(self._probe_override(health_url))
            if healthy:
                print("[JARVIS-DESKTOP] Core online", flush=True)
            return healthy
        context = self._ssl_context() if health_url.startswith("https://") else None
        request = urllib.request.Request(health_url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=1.5, context=context) as response:
                if response.status != 200:
                    print(f"[JARVIS-DESKTOP] Health failed: HTTP {response.status}",
                          flush=True)
                    return False
                payload = json.loads(response.read().decode("utf-8"))
                self._last_health = payload if isinstance(payload, dict) else None
                healthy = (isinstance(payload, dict)
                           and payload.get("ok") is True
                           and payload.get("gateway") == "running"
                           and (self.runtime_profile is None
                                or payload.get("runtime_profile") == self.runtime_profile))
                if healthy:
                    print("[JARVIS-DESKTOP] Core online", flush=True)
                else:
                    print("[JARVIS-DESKTOP] Health failed: invalid gateway payload",
                          flush=True)
                return healthy
        except (OSError, ValueError, urllib.error.URLError) as exc:
            self._last_health = None
            reason = getattr(exc, "reason", exc)
            print("[JARVIS-DESKTOP] Health failed: "
                  f"{type(reason).__name__}: {reason}", flush=True)
            return False

    @staticmethod
    def _port_in_use(port=8766, host="127.0.0.1"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            return sock.connect_ex((str(host), int(port))) == 0

    def _web_hosts(self):
        return ("127.0.0.1",)

    def probe_ui(self, origin):
        target = ui_url(origin)
        print(f"[JARVIS-DESKTOP] UI probe: {target}", flush=True)
        if self._ui_probe_override:
            return bool(self._ui_probe_override(target))
        request = urllib.request.Request(target, method="GET")
        try:
            with urllib.request.urlopen(
                    request, timeout=2.5, context=self._ssl_context()) as response:
                healthy = response.status == 200
                if not healthy:
                    print(f"[JARVIS-DESKTOP] UI failed: HTTP {response.status}",
                          flush=True)
                return healthy
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            print("[JARVIS-DESKTOP] UI failed: "
                  f"{type(reason).__name__}: {reason}", flush=True)
            return False

    def resolve_ui_origin(self):
        for host in self._web_hosts():
            origin = f"https://{host}:8765"
            if self.probe_ui(origin):
                print(f"[JARVIS-DESKTOP] UI URL: {ui_url(origin)}", flush=True)
                return origin
        return None

    def find_online_core(self):
        if self.probe(HTTPS_HEALTH_URL):
            payload = self._last_health or {}
            capabilities = set(payload.get("capabilities") or ())
            if self.required_capabilities - capabilities:
                self._replace_stale_core(payload)
                return None
            self.origin = self.resolve_ui_origin()
            if not self.origin:
                raise CoreLaunchError(
                    "O Gateway está online, mas a jarvis_ui não respondeu por HTTPS "
                    "na porta 8765 em nenhum host canônico.")
            self._adopted_health = payload
            return self.origin
        return None

    def _replace_stale_core(self, health):
        instance_id = str(health.get("runtime_instance_id") or "")
        pid = health.get("pid")
        capabilities = set(health.get("capabilities") or ())
        if (not instance_id or not pid or
                "CORE_LIFECYCLE_CONTROL" not in capabilities):
            raise CoreLaunchError(
                "O Core existente não anuncia o lifecycle cooperativo necessário. "
                "Não será encerrado nem substituído automaticamente; requer a "
                "transição humana única do Core antigo.")
        if not self.lifecycle_token:
            raise CoreLaunchError(
                "O Core existente precisa ser substituído, mas a identidade Desktop "
                "persistida não está disponível para autorizar o shutdown.")
        if (self.runtime_profile and
                health.get("runtime_profile") != self.runtime_profile):
            raise CoreLaunchError("O Core existente está em perfil incompatível.")

        request_id = str(uuid.uuid4())
        payload = json.dumps({"runtime_instance_id": instance_id,
                              "request_id": request_id,
                              "issued_at": time.time()}).encode("utf-8")
        request = urllib.request.Request(
            HTTPS_SHUTDOWN_URL, data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.lifecycle_token},
            method="POST")
        try:
            with urllib.request.urlopen(
                    request, timeout=5, context=self._ssl_context()) as response:
                result = json.loads(response.read().decode("utf-8"))
                if (response.status != 202 or not result.get("ok") or
                        result.get("runtime_instance_id") != instance_id or
                        int(result.get("pid", -1)) != int(pid)):
                    raise CoreLaunchError("O Core não confirmou o shutdown solicitado.")
        except urllib.error.HTTPError as exc:
            raise CoreLaunchError(
                f"O Core recusou o shutdown cooperativo (HTTP {exc.code}).") from exc
        except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
            raise CoreLaunchError(
                f"Falha no shutdown cooperativo ({type(exc).__name__}).") from exc

        deadline = time.monotonic() + min(self.timeout, 20.0)
        while time.monotonic() < deadline:
            if (not self._port_in_use(8766) and
                    not self._port_in_use(8765) and
                    not self._pid_exists(int(pid))):
                self._last_health = None
                return
            time.sleep(0.2)
        raise CoreLaunchError(
            "O shutdown foi aceito, mas o processo/portas não foram liberados "
            "dentro do limite; nenhum Core substituto será iniciado.")

    @staticmethod
    def _pid_exists(pid):
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, ValueError, TypeError):
            return False

    def ensure_online(self):
        online = self.find_online_core()
        if online:
            return online
        if self._port_in_use(8766):
            raise CoreLaunchError(
                "A porta 8766 está ocupada, mas o health do Gateway falhou. "
                "Consulte o log [JARVIS-DESKTOP] antes de reiniciar o Core.")
        server = self.root / "server_agent.py"
        if not server.is_file():
            raise CoreLaunchError(f"Runtime não encontrado: {server}")
        child_env = os.environ.copy()
        child_env["GOLDEN_SSL"] = "1"
        child_env["GOLDEN_GATEWAY_LAN"] = "1"
        print("[JARVIS-DESKTOP] Starting Core", flush=True)
        print("[JARVIS-DESKTOP] GOLDEN_SSL=1", flush=True)
        print("[JARVIS-DESKTOP] GOLDEN_GATEWAY_LAN=1", flush=True)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._spawn_attempt_id = uuid.uuid4().hex
        self._shutdown_requested = False
        boot_log("CORE_SPAWN " + json.dumps({
            "attempt_id": self._spawn_attempt_id,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid": None, "executable": self.python_executable,
            "runtime_profile": self.runtime_profile or "",
        }, sort_keys=True))
        command = [self.python_executable, str(server), "--port", "8765"]
        if self.runtime_profile:
            command.extend(["--runtime-profile", self.runtime_profile])
        self.process = self._popen(
            command,
            cwd=str(self.root), env=child_env, creationflags=flags,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
        )
        child_pid = getattr(self.process, "pid", None)
        if not isinstance(child_pid, (int, str)):
            child_pid = None
        boot_log("CORE_SPAWNED " + json.dumps({
            "attempt_id": self._spawn_attempt_id,
            "pid": child_pid,
            "executable": self.python_executable,
            "runtime_profile": self.runtime_profile or "",
        }, sort_keys=True))
        self._start_process_diagnostics(self.process, self._spawn_attempt_id)
        print(f"[JARVIS-DESKTOP] Core PID={getattr(self.process, 'pid', 'unknown')}",
              flush=True)
        self._adopted_health = None
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.process = None
                raise CoreLaunchError(f"O runtime encerrou durante a inicialização ({code}).")
            online = self.find_online_core()
            if online:
                return online
            time.sleep(0.25)
        self.stop_owned_core()
        raise CoreLaunchError(f"O Core não respondeu por HTTPS em {self.timeout:g}s.")

    def stop_owned_core(self):
        process = self.process
        adopted_health = self._adopted_health
        if process is None and adopted_health is None:
            self.process = None
            return True
        if process is not None and process.poll() is not None:
            self.process = None
            return True
        health = self._last_health or adopted_health or {}
        if not self.lifecycle_token or not health.get("runtime_instance_id"):
            print("[JARVIS-DESKTOP] Core remains running: no authenticated "
                  "cooperative shutdown identity is available.", flush=True)
            return False
        try:
            self._shutdown_requested = True
            self._replace_stale_core(health)
            if process is not None:
                process.wait(timeout=8)
        except (CoreLaunchError, subprocess.TimeoutExpired) as exc:
            print(f"[JARVIS-DESKTOP] Core shutdown not confirmed: {exc}", flush=True)
            return False
        self.process = None
        self._adopted_health = None
        return True

    @staticmethod
    def _sanitize_process_line(line):
        text = str(line or "").strip().replace("\x00", "")[:512]
        lowered = text.lower()
        for marker in ("authorization:", "bearer ", "api_key=", "token="):
            index = lowered.find(marker)
            if index >= 0:
                end = text.find(" ", index + len(marker))
                text = text[:index + len(marker)] + "[REDACTED]" if end < 0 else text[:index + len(marker)] + "[REDACTED]" + text[end:]
                lowered = text.lower()
        return text

    def _start_process_diagnostics(self, process, attempt_id):
        for stream_name in ("stdout", "stderr"):
            stream = getattr(process, stream_name, None)
            if isinstance(stream, io.TextIOBase):
                thread = threading.Thread(
                    target=self._read_process_stream,
                    args=(stream, stream_name, attempt_id),
                    name=f"jarvis-core-{stream_name}", daemon=True)
                thread.start()
        if hasattr(process, "wait"):
            self._process_watch = threading.Thread(
                target=self._watch_process, args=(process, attempt_id),
                name="jarvis-core-exit-watch", daemon=True)
            self._process_watch.start()

    @classmethod
    def _read_process_stream(cls, stream, stream_name, attempt_id):
        emitted = 0
        try:
            for line in iter(stream.readline, ""):
                if emitted < 100:
                    boot_log("CORE_OUTPUT " + json.dumps({
                        "attempt_id": attempt_id, "stream": stream_name,
                        "line": cls._sanitize_process_line(line),
                    }, ensure_ascii=False, sort_keys=True))
                    emitted += 1
                elif emitted == 100:
                    boot_log("CORE_OUTPUT_SUPPRESSED " + json.dumps({
                        "attempt_id": attempt_id, "stream": stream_name,
                    }, sort_keys=True))
                    emitted += 1
        except (OSError, ValueError):
            return

    def _watch_process(self, process, attempt_id):
        try:
            exit_code = process.wait()
        except Exception as exc:
            boot_log("CORE_EXIT_WATCH_FAILED " + json.dumps({
                "attempt_id": attempt_id, "error": type(exc).__name__,
            }, sort_keys=True))
            return
        boot_log("CORE_EXIT " + json.dumps({
            "attempt_id": attempt_id, "exit_code": exit_code,
            "classification": "expected" if self._shutdown_requested else "unexpected",
        }, sort_keys=True))

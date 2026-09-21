"""Locate or launch the existing server_agent runtime exactly once."""
from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .settings import studio_root, ui_url


HTTPS_HEALTH_URL = "https://127.0.0.1:8766/health"
HTTPS_UI_ORIGIN = "https://127.0.0.1:8765"


class CoreLaunchError(RuntimeError):
    pass


class CoreLauncher:
    def __init__(self, root=None, python_executable=None, popen=subprocess.Popen,
                 timeout=45.0, probe=None, ui_probe=None, host_provider=None):
        self.root = Path(root or studio_root()).resolve()
        self.python_executable = str(
            python_executable or self._default_python_executable())
        self._popen = popen
        self.timeout = float(timeout)
        self._probe_override = probe
        self._ui_probe_override = ui_probe
        self._host_provider = host_provider
        self.process = None
        self.origin = None

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
                healthy = (isinstance(payload, dict)
                           and payload.get("ok") is True
                           and payload.get("gateway") == "running")
                if healthy:
                    print("[JARVIS-DESKTOP] Core online", flush=True)
                else:
                    print("[JARVIS-DESKTOP] Health failed: invalid gateway payload",
                          flush=True)
                return healthy
        except (OSError, ValueError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            print("[JARVIS-DESKTOP] Health failed: "
                  f"{type(reason).__name__}: {reason}", flush=True)
            return False

    @staticmethod
    def _port_in_use(port=8766):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            return sock.connect_ex(("127.0.0.1", int(port))) == 0

    def _web_hosts(self):
        hosts = ["127.0.0.1"]
        try:
            if self._host_provider:
                lan_host = self._host_provider()
            else:
                from jarvis_core.lan_config import get_best_private_ip, get_lan_config
                config = get_lan_config()
                lan_host = (config.bind_address if config.enabled
                            else get_best_private_ip())
            lan_host = str(lan_host or "").strip()
            if lan_host and lan_host not in hosts:
                hosts.append(lan_host)
        except Exception as exc:
            print("[JARVIS-DESKTOP] UI host discovery failed: "
                  f"{type(exc).__name__}: {exc}", flush=True)
        return tuple(hosts)

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
            self.origin = self.resolve_ui_origin()
            if not self.origin:
                raise CoreLaunchError(
                    "O Gateway está online, mas a jarvis_ui não respondeu por HTTPS "
                    "na porta 8765 em nenhum host canônico.")
            return self.origin
        return None

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
        self.process = self._popen(
            [self.python_executable, str(server), "--port", "8765"],
            cwd=str(self.root), env=child_env, creationflags=flags,
        )
        print(f"[JARVIS-DESKTOP] Core PID={getattr(self.process, 'pid', 'unknown')}",
              flush=True)
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
        process, self.process = self.process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

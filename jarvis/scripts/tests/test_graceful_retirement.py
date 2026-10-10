import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import psutil
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "graceful_retirement.py"
spec = importlib.util.spec_from_file_location("retirement", SCRIPT)
retirement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retirement)


@pytest.mark.parametrize("members", [[1], [2], [1, 2, 3], []])
def test_shared_or_missing_console_refused(members):
    with pytest.raises(RuntimeError):
        retirement.require_exclusive_console(members, 1, 2)


def test_exclusive_console():
    retirement.require_exclusive_console([1, 2], 1, 2)


def test_stale_pid_refused():
    with pytest.raises(RuntimeError, match="creation time"):
        retirement.verify_identity(os.getpid(), 0, sys.executable, Path.cwd(), [], 0)


@pytest.mark.skipif(os.name != "nt", reason="Windows console lifecycle")
def test_real_uvicorn_lifespan_graceful_exit(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    marker = tmp_path / "lifespan.txt"
    fixture = Path(__file__).with_name("retirement_fixture.py")
    fixture_python = sys._base_executable
    command = [fixture_python, str(fixture), str(port), str(marker)]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(command, cwd=tmp_path, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE,
                                   startupinfo=startup)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                assert process.poll() is None, "Fixture exited before becoming ready"
                if marker.exists() and any(c.status == psutil.CONN_LISTEN and c.laddr.port == port
                                          for c in psutil.net_connections(kind="tcp")):
                    break
                time.sleep(0.1)
            assert marker.exists(), "Fixture did not start"
            created = psutil.Process(process.pid).create_time()
            helper = (
                "import importlib.util; "
                f"s=importlib.util.spec_from_file_location('r',{str(SCRIPT)!r}); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                f"m.signal_and_wait({process.pid},{created!r},{fixture_python!r},"
                f"{str(tmp_path)!r},{command!r},{port},20)"
            )
            result = subprocess.run([sys.executable, "-c", helper], capture_output=True,
                                    text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            assert "PROCESS_EXITED_VOLUNTARILY" in result.stdout
            process.wait(timeout=5)
            assert marker.read_text() == "lifespan_closed"
        finally:
            # The fixture has its own cooperative deadline. Never force cleanup.
            process.wait(timeout=50)
    assert "Application shutdown complete" in (tmp_path / "server.log").read_text()

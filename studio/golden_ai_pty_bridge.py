import os
import sys
import json
import time
import threading
import traceback

ROOT = r"C:\GoldenAI"
APP = os.path.join(ROOT, "app")
ENGINE = os.path.join(APP, "golden_ai.py")
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

_write_lock = threading.Lock()
_stop = threading.Event()
_pty = None


def emit(kind, **payload):
    obj = {"type": kind}
    obj.update(payload)
    line = json.dumps(obj, ensure_ascii=False)
    with _write_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def reader_loop():
    global _pty
    while not _stop.is_set():
        try:
            if _pty is None:
                time.sleep(0.05)
                continue

            if not _pty.isalive():
                emit("status", status="engine_exited")
                _stop.set()
                break

            data = _pty.read()
            if data:
                emit("output", text=str(data))
            else:
                time.sleep(0.02)
        except Exception as exc:
            # Algumas implementações podem lançar exceção transitória quando
            # não há dados disponíveis. Só encerramos se o processo morreu.
            try:
                alive = bool(_pty and _pty.isalive())
            except Exception:
                alive = False

            if not alive:
                emit("status", status="engine_exited")
                _stop.set()
                break

            time.sleep(0.03)


def main():
    global _pty

    try:
        from winpty import PTY
    except Exception as exc:
        emit(
            "fatal",
            message="pywinpty/winpty não está disponível.",
            detail=f"{type(exc).__name__}: {exc}"
        )
        return 2

    if not os.path.exists(PYTHON):
        emit("fatal", message="Python da GoldenAI não encontrado.", detail=PYTHON)
        return 3

    if not os.path.exists(ENGINE):
        emit("fatal", message="golden_ai.py não encontrado.", detail=ENGINE)
        return 4

    try:
        os.chdir(APP)

        # ConPTY real. O motor passa a enxergar um terminal interativo,
        # igual ao comportamento do BAT/Windows Terminal.
        _pty = PTY(180, 45)

        cmd = f'"{PYTHON}" -u "{ENGINE}"'
        _pty.spawn(cmd)

        emit(
            "status",
            status="pty_started",
            engine=ENGINE,
            python=PYTHON,
            cwd=APP
        )

        t = threading.Thread(target=reader_loop, daemon=True)
        t.start()

        for raw in sys.stdin:
            if _stop.is_set():
                break

            raw = raw.strip()
            if not raw:
                continue

            try:
                msg = json.loads(raw)
            except Exception as exc:
                emit("bridge_error", message=f"JSON inválido: {exc}")
                continue

            kind = msg.get("type")

            if kind == "send":
                text = str(msg.get("text", ""))
                try:
                    # Enter real no console do Windows.
                    _pty.write(text + "\r\n")
                    emit("status", status="sent")
                except Exception as exc:
                    emit(
                        "bridge_error",
                        message=f"Falha ao escrever no PTY: {type(exc).__name__}: {exc}"
                    )

            elif kind == "stop":
                try:
                    if _pty and _pty.isalive():
                        _pty.write("sair\r\n")
                except Exception:
                    pass
                _stop.set()
                break

            elif kind == "ping":
                emit(
                    "pong",
                    alive=bool(_pty and _pty.isalive())
                )

        _stop.set()
        try:
            t.join(timeout=1.0)
        except Exception:
            pass

        return 0

    except Exception as exc:
        emit(
            "fatal",
            message=f"Falha ao criar pseudo-terminal: {type(exc).__name__}: {exc}",
            detail=traceback.format_exc()
        )
        return 10


if __name__ == "__main__":
    raise SystemExit(main())

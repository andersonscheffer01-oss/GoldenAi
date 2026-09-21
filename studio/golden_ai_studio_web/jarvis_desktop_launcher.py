"""PyInstaller-friendly entry point for the JARVIS Desktop shell."""
from jarvis_desktop.web_app import main


if __name__ == "__main__":
    raise SystemExit(main())

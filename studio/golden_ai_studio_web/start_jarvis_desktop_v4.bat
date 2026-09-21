@echo off
REM Golden Jarvis Desktop V4 - launcher de desenvolvimento (venv do Golden, sem EXE)
set VENV_PY=C:\GoldenAI\.venv\Scripts\python.exe
set APP_DIR=C:\GoldenAI\studio\golden_ai_studio_web
"%VENV_PY%" -c "import PySide6" || (
  echo [ERRO] PySide6 nao encontrado no venv do Golden.
  pause
  exit /b 1
)
cd /d "%APP_DIR%" || exit /b 1
"%VENV_PY%" -m jarvis_desktop.app_v4
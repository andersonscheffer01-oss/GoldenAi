@echo off
setlocal
cd /d "%~dp0"

set "LAN_IP="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\detect_local_ipv4.ps1" -FirstOnly`) do if not defined LAN_IP set "LAN_IP=%%I"

cd /d "%~dp0backend"

if exist "..\.venv\Scripts\activate.bat" (
  call "..\.venv\Scripts\activate.bat"
) else (
  echo Ambiente virtual nao encontrado em C:\GoldenAI\jarvis\.venv
  echo Usando o Python disponivel no sistema.
)

echo.
echo Iniciando Golden Jarvis para acesso local e pela rede privada.
echo Computador: http://127.0.0.1:8780/app
if defined LAN_IP (
  echo iPhone na mesma rede Wi-Fi: http://%LAN_IP%:8780/app
) else (
  echo Nenhum IPv4 privado ativo foi encontrado. O acesso local continuara disponivel.
)
echo Swagger: http://127.0.0.1:8780/docs
echo Acesso remoto funciona somente na mesma rede local e pode depender do Firewall do Windows.
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 8780
if errorlevel 1 (
  echo.
  echo Erro ao iniciar o Golden Jarvis.
  pause
)

endlocal

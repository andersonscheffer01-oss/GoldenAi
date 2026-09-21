@echo off
title Golden AI - Auto Start
echo.
echo ═══════════════════════════════════════════════
echo   Golden AI - Iniciando Automaticamente...
echo ═══════════════════════════════════════════════
echo.

REM Verificar se MT5 ja esta rodando
tasklist /FI "IMAGENAME eq terminal64.exe" 2>NUL | find /I "terminal64.exe" >NUL
if %ERRORLEVEL% == 0 (
    echo [MT5] ✅ MetaTrader 5 ja esta aberto
) else (
    echo [MT5] Abrindo MetaTrader 5...
    start "" "C:\Program Files\MetaTrader 5\terminal64.exe"
    echo [MT5] Aguardando 10 segundos para MT5 inicializar...
    timeout /t 10 /nobreak >NUL
)

REM Reiniciar o servidor na porta 8765 a cada clique
echo [SERVER] Reiniciando servidor Golden AI...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do taskkill /PID %%P /F >NUL 2>&1
cd /d C:\GoldenAI
start "Golden AI Server" /B C:\GoldenAI\.venv\Scripts\python.exe studio\golden_ai_studio_web\server_agent.py --port 8765
echo [SERVER] Aguardando 5 segundos para servidor inicializar...
timeout /t 5 /nobreak >NUL

echo.
echo ═══════════════════════════════════════════════
echo   ✅ Golden AI Pronto!
echo.
echo   Dashboard: http://127.0.0.1:8765/dashboard.html
echo   Studio:    http://127.0.0.1:8765/studio_v7.html
echo ═══════════════════════════════════════════════
echo.

REM Abrir dashboard no navegador
start http://127.0.0.1:8765/dashboard.html

echo Pressione Ctrl+C para encerrar o servidor...
pause >NUL

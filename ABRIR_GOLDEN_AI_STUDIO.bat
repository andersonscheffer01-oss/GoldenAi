@echo off
title Golden AI Studio
echo.
echo  ========================================
echo   Golden AI Studio - Iniciando...
echo  ========================================
echo.

cd /d C:\GoldenAI\studio\golden_ai_studio_web

echo [1/2] Reiniciando servidor API...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
start /b C:\GoldenAI\.venv\Scripts\python.exe server_agent.py --port 8765 > nul 2>&1

echo [2/2] Aguardando servidor...
timeout /t 2 /nobreak > nul

echo.
echo  Servidor rodando em: http://127.0.0.1:8765
echo  Abrindo navegador...
echo.

start http://127.0.0.1:8765/dashboard.html

echo.
echo  ========================================
echo   Golden AI Studio esta aberto!
echo   Para fechar, feche esta janela.
echo  ========================================
echo.
pause

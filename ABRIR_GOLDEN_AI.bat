@echo off
title Golden AI - Inicializador Seguro
cd /d C:\GoldenAI\app

if not exist "C:\GoldenAI\.venv\Scripts\python.exe" (
    echo.
    echo ERRO: Python do ambiente GoldenAI nao foi encontrado.
    echo Esperado: C:\GoldenAI\.venv\Scripts\python.exe
    echo.
    pause
    exit /b 1
)

if not exist "C:\GoldenAI\app\golden_ai.py" (
    echo.
    echo ERRO: golden_ai.py nao foi encontrado.
    echo Esperado: C:\GoldenAI\app\golden_ai.py
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo INICIANDO GOLDEN AI PELO AMBIENTE CORRETO
echo ============================================================
echo.

"C:\GoldenAI\.venv\Scripts\python.exe" "C:\GoldenAI\app\golden_ai.py"

echo.
echo ============================================================
echo A GOLDEN AI FOI ENCERRADA.
echo ============================================================
pause

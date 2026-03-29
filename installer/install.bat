@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  Asistente IA GBM — Instalador (Windows)
REM  No requiere internet. No requiere Python ni Node.js pre-instalados.
REM ─────────────────────────────────────────────────────────────────────────────
title Asistente IA GBM — Instalador
cd /d "%~dp0"

echo.
echo  Asistente IA GBM
echo  Verificando bundle...
echo.

if not exist "assets\" (
    echo [ERROR] Carpeta "assets" no encontrada.
    echo Ejecuta: python build.py  (en maquina con internet)
    pause & exit /b 1
)
if not exist "assets\python\python-embed-win.zip" (
    echo [ERROR] Python embeddable no encontrado.
    echo Ejecuta: python build.py
    pause & exit /b 1
)
if not exist "assets\node\node-win.zip" (
    echo [ERROR] Node.js no encontrado en assets\node\
    echo Ejecuta: python build.py
    pause & exit /b 1
)
if not exist "assets\claude_code\node_modules.zip" (
    echo [ERROR] Claude Code no encontrado en assets\claude_code\
    echo Ejecuta: python build.py
    pause & exit /b 1
)
if not exist "assets\project\asistente\" (
    echo [ERROR] Asistente IA no encontrado en assets\project\asistente\
    echo Ejecuta: python build.py
    pause & exit /b 1
)

echo  Bundle OK. Iniciando instalador grafico...
echo.
powershell.exe -ExecutionPolicy Bypass -NonInteractive -File "%~dp0install.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [!] Instalador termino con codigo: %errorlevel%
    pause
)
exit /b %errorlevel%

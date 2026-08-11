@echo off
rem Lanza LLMJarvis sin ventana de consola.
cd /d "%~dp0"

rem Prefiere el entorno aislado que arma setup.ps1; si no existe, el Python del sistema.
set "PYW=pythonw.exe"
if exist ".venv\Scripts\pythonw.exe" set "PYW=.venv\Scripts\pythonw.exe"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

"%PY%" -c "import anthropic, keyboard, pystray" >nul 2>&1
if errorlevel 1 (
    echo Faltan dependencias. Corre INSTALAR.bat primero.
    pause
    exit /b 1
)

start "" "%PYW%" main.py

@echo off
rem Abre solo el panel de configuracion (sin arrancar el listener).
cd /d "%~dp0"

set "PYW=pythonw.exe"
if exist ".venv\Scripts\pythonw.exe" set "PYW=.venv\Scripts\pythonw.exe"

start "" "%PYW%" -m eve.gui

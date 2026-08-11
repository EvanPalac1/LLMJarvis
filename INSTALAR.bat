@echo off
rem Doble clic aca para instalar. Evita pelear con la politica de scripts de PowerShell.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause

@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare-DroneStream-Transfer.ps1"
if errorlevel 1 pause
endlocal
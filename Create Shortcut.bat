@echo off
REM Double-click me to put an "ILP Archive Namer" shortcut on the desktop
REM and in the Start menu. See "Create Shortcut.ps1" for options.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Create Shortcut.ps1" %*
pause

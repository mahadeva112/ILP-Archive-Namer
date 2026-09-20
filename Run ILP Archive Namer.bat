@echo off
REM Launch the ILP Archive Namer. Needs Python 3.8+ on PATH.
REM Uses pythonw.exe so no console window sticks around -- the server stops on
REM its own when you close the browser tab. Pass --console to keep a window.
setlocal
cd /d "%~dp0"

if /i "%~1"=="--console" (
  shift
  goto :console
)

where pythonw >nul 2>nul
if errorlevel 1 goto :nopython
start "" pythonw "%~dp0server.py" %*
exit /b 0

:console
where python >nul 2>nul
if errorlevel 1 goto :nopython
python "%~dp0server.py" %*
if errorlevel 1 pause
exit /b 0

:nopython
echo Python was not found on this computer.
echo Install Python 3 from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH" during setup, then run this file again.
echo.
pause
exit /b 1

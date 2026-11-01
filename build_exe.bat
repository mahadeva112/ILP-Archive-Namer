@echo off
REM Build a single-file Windows executable so translators need no Python.
REM Requires: pip install pyinstaller
REM --noconsole: the app is the browser page, so no console window is shown.
REM The server exits on its own a few seconds after the browser tab closes.
setlocal
cd /d "%~dp0"

python -m PyInstaller --noconfirm --clean --onefile ^
  --name "ILP-Archive-Namer" ^
  --icon "assets\ILP-Archive-Namer.ico" ^
  --add-data "data;data" ^
  --add-data "web;web" ^
  --noconsole ^
  server.py

echo.
if exist "dist\ILP-Archive-Namer.exe" (
  echo Built: dist\ILP-Archive-Namer.exe
  echo Copy that single file to any Windows machine and double-click it.
) else (
  echo Build failed. Run "pip install pyinstaller" and try again.
)
if /i not "%~1"=="nopause" pause

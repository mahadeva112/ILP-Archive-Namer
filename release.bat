@echo off
REM Publish a new version, so every copy of the app offers to update itself.
REM
REM   1. Raise __version__ in namer\__init__.py (for example 1.1.0 to 1.2.0).
REM   2. Write what changed in release-notes.txt. People see it in the app's
REM      update bar under "What's new".
REM   3. Commit and push.
REM   4. Double-click this file.
REM
REM Needs PyInstaller (pip install pyinstaller) and the GitHub CLI, signed in
REM once with "gh auth login". The release is tagged v<version> and carries
REM dist\ILP-Archive-Namer.exe; the app looks for exactly that file name.
setlocal
cd /d "%~dp0"

set "VER="
for /f "tokens=2 delims==" %%v in ('findstr /b /c:"__version__" namer\__init__.py') do set "VER=%%v"
set VER=%VER: =%
set VER=%VER:"=%
if "%VER%"=="" (
  echo Could not read __version__ from namer\__init__.py
  pause
  exit /b 1
)

where gh >nul 2>nul
if errorlevel 1 (
  echo The GitHub CLI "gh" is not installed. Get it from https://cli.github.com
  pause
  exit /b 1
)

gh release view v%VER% >nul 2>nul
if not errorlevel 1 (
  echo Release v%VER% already exists. Raise __version__ in namer\__init__.py first.
  pause
  exit /b 1
)

echo Building v%VER% ...
call build_exe.bat nopause
if not exist "dist\ILP-Archive-Namer.exe" (
  echo Build failed.
  pause
  exit /b 1
)

if exist release-notes.txt (
  gh release create v%VER% "dist\ILP-Archive-Namer.exe" --title "ILP Archive Namer v%VER%" --notes-file release-notes.txt
) else (
  gh release create v%VER% "dist\ILP-Archive-Namer.exe" --title "ILP Archive Namer v%VER%" --generate-notes
)
if errorlevel 1 (
  echo Publishing failed.
  pause
  exit /b 1
)

echo.
echo Published v%VER%. Open copies of the app will offer it the next time they start.
pause

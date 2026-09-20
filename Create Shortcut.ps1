<#
  Creates a pinnable Windows shortcut for the ILP Archive Namer.

  The shortcut targets python.exe directly (not the .bat) because Windows only
  lets you pin shortcuts whose target is an executable -- a .lnk pointing at a
  batch file has no "Pin to taskbar" option.

  Usage (from this folder):
    powershell -ExecutionPolicy Bypass -File ".\Create Shortcut.ps1"

  The shortcut is windowless by default: it runs pythonw.exe, so no console
  window appears alongside the browser. The server then quits by itself a few
  seconds after you close the browser tab.

  Options:
    -Console      run with python.exe, keeping a minimised console window you
                  can press Ctrl+C in
    -NoStartMenu  create the desktop shortcut only
#>
param(
  [switch]$Console,
  [switch]$NoStartMenu
)

$Windowless = -not $Console

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$name = 'ILP Archive Namer'
$icon = Join-Path $root 'assets\ILP-Archive-Namer.ico'
$exeName = if ($Windowless) { 'pythonw.exe' } else { 'python.exe' }

# --- locate a real python.exe -------------------------------------------------
# `where python` can resolve to the Microsoft Store alias, which is a 0-byte
# reparse point -- usable, but ask Python itself for its true location first.
$python = $null
try {
  $resolved = & python -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), '$exeName'))" 2>$null
  if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path $resolved)) { $python = $resolved }
} catch {}

if (-not $python) {
  try {
    $resolved = & py -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), '$exeName'))" 2>$null
    if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path $resolved)) { $python = $resolved }
  } catch {}
}

if (-not $python) {
  Write-Host ''
  Write-Host "Could not find $exeName on this computer." -ForegroundColor Red
  Write-Host 'Install Python 3.8+ from https://www.python.org/downloads/ and tick'
  Write-Host '"Add python.exe to PATH" during setup, then run this script again.'
  Write-Host ''
  exit 1
}

if (-not (Test-Path $icon)) {
  Write-Host "Icon not found at $icon -- the shortcut will use Python's icon." -ForegroundColor Yellow
  $icon = $null
}

# --- create the shortcuts -----------------------------------------------------
function New-AppShortcut([string]$path) {
  $dir = Split-Path -Parent $path
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  $shell = New-Object -ComObject WScript.Shell
  $lnk = $shell.CreateShortcut($path)
  $lnk.TargetPath = $python
  $lnk.Arguments = '"' + (Join-Path $root 'server.py') + '"'
  $lnk.WorkingDirectory = $root
  $lnk.Description = 'Rename ILP archive files to the naming spec'
  # 7 = minimised, so the console sits in the taskbar instead of on top of the
  # browser window the tool opens. 1 = normal (pythonw shows nothing anyway).
  $lnk.WindowStyle = if ($Windowless) { 1 } else { 7 }
  if ($icon) { $lnk.IconLocation = "$icon,0" }
  $lnk.Save()
  Write-Host "  Created: $path" -ForegroundColor Green
  return $path
}

Write-Host ''
Write-Host "Using: $python" -ForegroundColor Cyan
Write-Host ''

$desktop = New-AppShortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) "$name.lnk")

$startLnk = $null
if (-not $NoStartMenu) {
  $programs = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
  $startLnk = New-AppShortcut (Join-Path $programs "$name.lnk")
}

# --- pinning ------------------------------------------------------------------
# Windows 10/11 removed the "pin to taskbar"/"pin to start" shell verbs for
# scripted callers, so pinning has to be a manual click. Try anyway on the
# off chance the verb is present, then print instructions either way.
$pinned = $false
if ($startLnk) {
  try {
    $shellApp = New-Object -ComObject Shell.Application
    $folder = $shellApp.Namespace((Split-Path -Parent $startLnk))
    $item = $folder.ParseName((Split-Path -Leaf $startLnk))
    foreach ($verb in $item.Verbs()) {
      if ($verb.Name -replace '&', '' -match '^Pin to Start') { $verb.DoIt(); $pinned = $true }
    }
  } catch {}
}

Write-Host ''
if ($pinned) {
  Write-Host 'Pinned to Start.' -ForegroundColor Green
} else {
  Write-Host 'To pin it (Windows blocks scripts from doing this for you):' -ForegroundColor Yellow
  Write-Host '  Taskbar - right-click the desktop shortcut > Show more options > Pin to taskbar'
  Write-Host '  Start   - press Start, type "ILP Archive Namer", right-click the'
  Write-Host '            result > Pin to Start'
}
Write-Host ''

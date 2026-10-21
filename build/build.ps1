# Build the green portable XTime package and zip it.
#
# Usage (from the project root):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File build\build.ps1
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 -NoZip

param(
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Dist = Join-Path $Root "dist\XTime"
$Work = Join-Path $Root "build\work"
$Zip = Join-Path $Root "XTime-win64.zip"

if (-not (Test-Path $Python)) {
    throw "Virtual environment not found at $Python. Create .venv and install requirements first."
}

Write-Host "==> Cleaning previous build output"
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
if (Test-Path $Zip) { Remove-Item -Force $Zip }

Write-Host "==> Generating icon (optional if app.ico already exists)"
& $Python (Join-Path $Root "build\make_icon.py")

Write-Host "==> Running PyInstaller"
Push-Location $Root
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath (Join-Path $Root "dist") `
        --workpath $Work `
        (Join-Path $Root "build\XTime.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $Dist "XTime.exe"))) {
    throw "Build finished but XTime.exe was not produced."
}

Write-Host "==> Adding portable data template and documentation"
$Template = @'
{
  "version": 1,
  "sessions": [],
  "settings": {
    "last_mode": "countdown",
    "last_countdown": "00:25:00",
    "always_on_top": false,
    "window_pos": [200, 300],
    "window_scale": 1.0,
    "background_style": "faint_gray",
    "background_alpha": 0.18,
    "font_family": "JetBrains Mono",
    "font_weight": 700,
    "font_color": "#E8E8E8",
    "colon_color": "#888888",
    "colon_follow_digit": false,
    "blur_enabled": false,
    "sound_enabled": true,
    "confirm_on_exit": true,
    "fallback_notice_shown": false
  }
}
'@
# PowerShell 5.1's UTF8 encoding adds a BOM; JSON must start with a brace.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $Dist "data.json"), $Template, $utf8NoBom)
Copy-Item (Join-Path $Root "README.txt") (Join-Path $Dist "README.txt") -Force
Copy-Item (Join-Path $Root "THIRD_PARTY_LICENSES.txt") (Join-Path $Dist "THIRD_PARTY_LICENSES.txt") -Force

if ($NoZip) {
    Write-Host "==> Done (zip skipped): $Dist"
    exit 0
}

Write-Host "==> Compressing XTime-win64.zip"
& $Python (Join-Path $Root "build\zip_package.py") $Dist $Zip
if ($LASTEXITCODE -ne 0) { throw "Zip creation failed with exit code $LASTEXITCODE" }

$size = (Get-Item $Zip).Length
Write-Host ("==> Done: {0} ({1:N1} MB)" -f $Zip, ($size / 1MB))

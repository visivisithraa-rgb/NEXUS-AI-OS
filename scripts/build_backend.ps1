# NEXUS AI OS - Python Backend Packager
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Packaging NEXUS AI OS Python Backend" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$VenvPython = ".\.venv\Scripts\python.exe"
$PyInstaller = ".\.venv\Scripts\pyinstaller.exe"

if (-not (Test-Path $PyInstaller)) {
    Write-Error "PyInstaller not found in .venv! Run pip install pyinstaller first."
    exit 1
}

# Clean existing build directories if present
if (Test-Path "build\backend") {
    Write-Host "Cleaning previous build\backend..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "build\backend"
}

# Run PyInstaller
Write-Host "Executing PyInstaller with backend.spec..." -ForegroundColor Green
& $PyInstaller backend.spec --distpath build/backend --workpath build/pyinstaller_work --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# Verify output executable
$BuiltExe = "build\backend\nexus_backend\nexus_backend.exe"
if (Test-Path $BuiltExe) {
    Write-Host "SUCCESS: Backend compiled at $BuiltExe" -ForegroundColor Green
} else {
    Write-Error "Compilation output not found at $BuiltExe!"
    exit 1
}

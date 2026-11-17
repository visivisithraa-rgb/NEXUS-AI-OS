# NEXUS AI OS - Complete Desktop Application Rebuild Script
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " NEXUS AI OS - Desktop Rebuild & Package  " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Close any running instances if open
Write-Host "Checking for running instances..." -ForegroundColor Yellow
Stop-Process -Name "NEXUS AI OS", "nexus_backend" -ErrorAction SilentlyContinue

# 2. Compile Python Backend
Write-Host "Compiling Python Backend..." -ForegroundColor Green
powershell -ExecutionPolicy Bypass -File ./scripts/build_backend.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Backend compilation failed!"
    exit 1
}

# 3. Build Electron Desktop Package & NSIS Installer
Write-Host "Building Electron Desktop Application & Windows Installer..." -ForegroundColor Green
npm run build:installer
if ($LASTEXITCODE -ne 0) {
    Write-Error "Electron builder packaging failed!"
    exit 1
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " BUILD COMPLETED SUCCESSFULLY!" -ForegroundColor Green
Write-Host " Installer: dist-electron/NEXUS AI OS Setup 1.0.0.exe" -ForegroundColor Green
Write-Host " Standalone: dist-electron/win-unpacked/NEXUS AI OS.exe" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan

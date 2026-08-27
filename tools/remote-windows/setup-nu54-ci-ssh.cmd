@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem @brief NU54DK clean Windows SSH 설정을 관리자 권한으로 실행합니다.
cd /d "%~dp0"

set "NU54_SETUP_VERSION=2026-08-27.4"
set "NU54_PS_SCRIPT=%~dp0setup-nu54-ci-ssh.ps1"
set "NU54_PUBLIC_KEY=%~dp0nu54dk_m10_ed25519.pub"

echo [NU54-SSH] Package version: %NU54_SETUP_VERSION%

if not exist "%NU54_PS_SCRIPT%" (
    echo [NU54-SSH] Missing file: %NU54_PS_SCRIPT%
    pause
    exit /b 2
)

if not exist "%NU54_PUBLIC_KEY%" (
    echo [NU54-SSH] Missing file: %NU54_PUBLIC_KEY%
    echo Place nu54dk_m10_ed25519.pub in the same directory as this CMD file.
    pause
    exit /b 2
)

rem @brief 현재 프로세스가 관리자 권한인지 확인하고 필요하면 UAC 승격을 요청합니다.
powershell.exe -NoProfile -Command "$p=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()); if($p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 (
    echo [NU54-SSH] Requesting administrator privileges...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

echo [NU54-SSH] Installing and configuring OpenSSH Server...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%NU54_PS_SCRIPT%" -PublicKeyPath "%NU54_PUBLIC_KEY%" -AllowedRemoteAddress "LocalSubnet" -GenerateAccountPassword
set "NU54_EXIT_CODE=%ERRORLEVEL%"

if not "%NU54_EXIT_CODE%"=="0" (
    echo.
    echo [NU54-SSH] Setup failed with exit code %NU54_EXIT_CODE%.
    pause
    exit /b %NU54_EXIT_CODE%
)

echo.
echo [NU54-SSH] Setup completed. Keep this window open and record the IPv4 address and host fingerprint.
pause
exit /b 0

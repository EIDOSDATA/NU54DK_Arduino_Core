@echo off
setlocal EnableExtensions

rem @brief Arduino Boards Manager 설치 뒤 Nordic 개발 환경을 사용자 영역에 준비합니다.
set "NU54_INSTALLER=%~dp0tools\nu54-prerequisites\install-nordic.ps1"
set "NU54_PLATFORM_ROOT=%~dp0."

if not exist "%NU54_INSTALLER%" (
  echo NU54DK prerequisite installer was not found: "%NU54_INSTALLER%" 1>&2
  exit /b 2
)

powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%NU54_INSTALLER%" -PlatformRoot "%NU54_PLATFORM_ROOT%"
set "NU54_RESULT=%ERRORLEVEL%"

if not "%NU54_RESULT%"=="0" (
  echo NU54DK Nordic prerequisite installation failed with exit code %NU54_RESULT%. 1>&2
)

exit /b %NU54_RESULT%

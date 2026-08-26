@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"

set "NU54_PYTHON="

rem NCS Manager가 지정한 Python을 우선 사용한다.
if defined NUCODE_PYTHON if exist "%NUCODE_PYTHON%" set "NU54_PYTHON=%NUCODE_PYTHON%"

rem 일반 Arduino IDE 프로세스에서도 동작하도록 설치된 NCS bundle을 찾는다.
if not defined NU54_PYTHON if defined NUCODE_TOOLCHAIN_ROOT if exist "%NUCODE_TOOLCHAIN_ROOT%\opt\bin\python.exe" set "NU54_PYTHON=%NUCODE_TOOLCHAIN_ROOT%\opt\bin\python.exe"

for /d %%D in (C:\ncs\toolchains\*) do if not defined NU54_PYTHON if exist "%%~fD\opt\bin\python.exe" set "NU54_PYTHON=%%~fD\opt\bin\python.exe"

if not defined NU54_PYTHON if exist "%LocalAppData%\Python\bin\python.exe" set "NU54_PYTHON=%LocalAppData%\Python\bin\python.exe"

if not defined NU54_PYTHON (
  echo nu54-builder: Python executable was not found. 1>&2
  exit /b 2
)

"%NU54_PYTHON%" "%~dp0src\nu54_builder.py" %*
exit /b %errorlevel%

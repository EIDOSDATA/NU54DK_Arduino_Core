@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"

set "NU54_PYTHON="

if defined NUCODE_PYTHON if exist "%NUCODE_PYTHON%" set "NU54_PYTHON=%NUCODE_PYTHON%"

if not defined NU54_PYTHON if defined NUCODE_TOOLCHAIN_ROOT if exist "%NUCODE_TOOLCHAIN_ROOT%\opt\bin\python.exe" set "NU54_PYTHON=%NUCODE_TOOLCHAIN_ROOT%\opt\bin\python.exe"

if not defined NU54_PYTHON if defined USERPROFILE if exist "%USERPROFILE%\ncs\toolchains\dcbdc366a1\opt\bin\python.exe" set "NU54_PYTHON=%USERPROFILE%\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"

if defined USERPROFILE for /d %%D in ("%USERPROFILE%\ncs\toolchains\*") do if not defined NU54_PYTHON if exist "%%~fD\opt\bin\python.exe" set "NU54_PYTHON=%%~fD\opt\bin\python.exe"

for /d %%D in (C:\ncs\toolchains\*) do if not defined NU54_PYTHON if exist "%%~fD\opt\bin\python.exe" set "NU54_PYTHON=%%~fD\opt\bin\python.exe"

if not defined NU54_PYTHON if exist "%LocalAppData%\Python\bin\python.exe" set "NU54_PYTHON=%LocalAppData%\Python\bin\python.exe"

if not defined NU54_PYTHON (
  echo nu54-builder: Python executable was not found. 1>&2
  exit /b 2
)

for %%I in ("%NU54_PYTHON%") do set "NU54_PYTHON_DIR=%%~dpI"
set "PATH=%NU54_PYTHON_DIR%;%PATH%"

"%NU54_PYTHON%" -I "%~dp0src\nu54_builder.py" %*
exit /b %errorlevel%

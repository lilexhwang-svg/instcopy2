@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
title instcopy server
cd /d "%~dp0instagram_db_first" || goto :fail

if not defined INSTCOPY_PYTHON goto :find_python
"%INSTCOPY_PYTHON%" -c "import sys, venv; raise SystemExit(sys.version_info < (3,10))" >nul 2>&1
if errorlevel 1 goto :invalid_python
"%INSTCOPY_PYTHON%" bootstrap_env.py %*
if errorlevel 1 goto :fail
exit /b 0

:find_python
py -3 -c "import sys, venv; raise SystemExit(sys.version_info < (3,10))" >nul 2>&1
if errorlevel 1 goto :try_python
py -3 bootstrap_env.py %*
if errorlevel 1 goto :fail
exit /b 0

:try_python
python -c "import sys, venv; raise SystemExit(sys.version_info < (3,10))" >nul 2>&1
if errorlevel 1 goto :missing_python
python bootstrap_env.py %*
if errorlevel 1 goto :fail
exit /b 0

:invalid_python
echo [ERROR] INSTCOPY_PYTHON does not point to a working Python 3.10+ installation.
goto :fail

:missing_python
echo [ERROR] A working Python 3.10+ installation was not found on this PC.
echo Install Python from https://www.python.org and enable Add python.exe to PATH.
goto :fail

:fail
echo.
echo Something went wrong. Read the message above.
pause
exit /b 1

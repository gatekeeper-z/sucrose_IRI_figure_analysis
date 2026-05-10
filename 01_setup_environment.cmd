@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================================
echo  IRI Analyzer - environment setup
echo ============================================================
echo.

call :find_python
if not defined BASE_PY (
  echo Python 3.10+ was not found.
  call :install_with_winget "Python.Python.3.12" "Python"
  call :find_python
)
if not defined BASE_PY (
  echo.
  echo Python still was not found.
  echo Opening the Python download page. Install Python, then double-click this script again.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating local Python virtual environment: .venv
  %BASE_PY% -m venv .venv
  if %ERRORLEVEL% NEQ 0 goto fail
) else (
  echo Python virtual environment already exists: .venv
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

echo.
echo Checking Python dependencies...
"%VENV_PY%" -c "import iri_analyzer, fastapi, uvicorn, cv2, numpy, pandas, yaml, matplotlib" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo Installing Python package and dependencies...
  "%VENV_PY%" -m pip install --upgrade pip
  if %ERRORLEVEL% NEQ 0 goto fail
  "%VENV_PY%" -m pip install -e ".[test]"
  if %ERRORLEVEL% NEQ 0 goto fail
) else (
  echo Python dependencies are available.
)

call :find_npm
if not defined HAS_NPM (
  echo.
  echo Node.js/npm was not found.
  call :install_with_winget "OpenJS.NodeJS.LTS" "Node.js LTS"
  call :find_npm
)
if not defined HAS_NPM (
  echo.
  echo Node.js/npm still was not found.
  echo Opening the Node.js download page. Install Node.js LTS, then double-click this script again.
  start "" "https://nodejs.org/"
  pause
  exit /b 1
)

echo.
echo Checking frontend dependencies...
cd web
if not exist "node_modules" (
  echo Installing frontend dependencies with npm ci...
  call npm ci
  if %ERRORLEVEL% NEQ 0 goto fail
) else (
  echo Frontend dependencies already exist: web\node_modules
)

echo.
echo Building frontend...
call npm run build
if %ERRORLEVEL% NEQ 0 goto fail
cd ..

echo.
echo Running quick verification tests...
"%VENV_PY%" -m pytest -q
if %ERRORLEVEL% NEQ 0 goto fail

echo.
echo ============================================================
echo  Setup complete.
echo  You can now double-click 02_start_web_ui.cmd
echo ============================================================
pause
exit /b 0

:fail
cd /d "%~dp0"
echo.
echo Setup failed. Please review the messages above.
pause
exit /b 1

:find_python
set "BASE_PY="
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    set "BASE_PY=python"
    exit /b 0
  )
)
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    set "BASE_PY=py -3"
    exit /b 0
  )
)
exit /b 0

:find_npm
set "HAS_NPM="
where npm >nul 2>nul
if %ERRORLEVEL% EQU 0 set "HAS_NPM=1"
exit /b 0

:install_with_winget
where winget >nul 2>nul
if %ERRORLEVEL% NEQ 0 exit /b 0
echo.
echo Trying to install %~2 automatically with winget...
winget install -e --id %~1 --accept-package-agreements --accept-source-agreements
exit /b 0

@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0" || (
  echo Failed to enter project directory: %~dp0
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  IRI Analyzer - environment setup
echo ============================================================
echo.

call :find_python
if not defined PY_EXE (
  echo Python 3.10+ was not found.
  call :install_with_winget "Python.Python.3.12" "Python"
  call :find_python
)
if not defined PY_EXE (
  echo.
  echo Python still was not found.
  echo Opening the Python download page. Install Python 3.10+, then double-click this script again.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)
echo Python command: "%PY_EXE%" %PY_ARGS%

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo Creating local Python virtual environment: .venv
  "%PY_EXE%" %PY_ARGS% -m venv ".venv"
  if errorlevel 1 goto fail
) else (
  echo Python virtual environment already exists: .venv
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo Virtual environment Python was not created: %VENV_PY%
  goto fail
)

echo.
echo Checking Python dependencies...
"%VENV_PY%" -c "import iri_analyzer, fastapi, uvicorn, cv2, numpy, pandas, yaml, matplotlib" >nul 2>nul
if errorlevel 1 (
  echo Installing Python package and dependencies...
  "%VENV_PY%" -m pip install -e .
  if errorlevel 1 goto fail
  "%VENV_PY%" -m pip install pytest
  if errorlevel 1 goto fail
) else (
  echo Python dependencies are available.
)

call :find_npm
if not defined NPM_CMD (
  echo.
  echo Node.js/npm was not found.
  call :install_with_winget "OpenJS.NodeJS.LTS" "Node.js LTS"
  call :find_npm
)
if not defined NPM_CMD (
  echo.
  echo Node.js/npm still was not found.
  echo Opening the Node.js download page. Install Node.js LTS, then double-click this script again.
  start "" "https://nodejs.org/"
  pause
  exit /b 1
)
echo npm command: "%NPM_CMD%"

echo.
echo Checking frontend dependencies...
if not exist "web\package.json" (
  echo Frontend project was not found: web\package.json
  goto fail
)
pushd web
if not exist "node_modules" (
  echo Installing frontend dependencies with npm ci...
  call "%NPM_CMD%" ci
  if errorlevel 1 (
    echo npm ci failed; trying npm install...
    call "%NPM_CMD%" install
    if errorlevel 1 goto fail
  )
) else (
  echo Frontend dependencies already exist: web\node_modules
)

echo.
echo Building frontend...
call "%NPM_CMD%" run build
if errorlevel 1 goto fail
popd

echo.
echo Running quick verification tests...
"%VENV_PY%" -m pip install pytest httpx
if errorlevel 1 goto fail
"%VENV_PY%" -m pytest -q
if errorlevel 1 goto fail

echo.
echo ============================================================
echo  Setup complete.
echo  You can now double-click 02_start_web_ui.cmd
echo ============================================================
pause
exit /b 0

:fail
popd >nul 2>nul
cd /d "%~dp0" >nul 2>nul
echo.
echo Setup failed. Please review the messages above.
pause
exit /b 1

:find_python
set "PY_EXE="
set "PY_ARGS="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARGS=-3"
    exit /b 0
  )
)
where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=python"
    set "PY_ARGS="
    exit /b 0
  )
)
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$roots=@($env:LOCALAPPDATA+'\Programs\Python',$env:ProgramFiles,${env:ProgramFiles(x86)}); $py=foreach($r in $roots){ if($r -and (Test-Path $r)){ Get-ChildItem -Path $r -Filter python.exe -Recurse -ErrorAction SilentlyContinue }}; $py | Where-Object { try { $v=& $_.FullName -c 'import sys; print(sys.version_info[:2] >= (3,10))' 2>$null; $v -eq 'True' } catch { $false } } | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do (
  if exist "%%P" (
    set "PY_EXE=%%P"
    set "PY_ARGS="
    exit /b 0
  )
)
exit /b 0

:find_npm
set "NPM_CMD="
for /f "delims=" %%N in ('where npm.cmd 2^>nul') do (
  if exist "%%N" (
    set "NPM_CMD=%%N"
    exit /b 0
  )
)
for /f "delims=" %%N in ('where npm 2^>nul') do (
  if exist "%%N" (
    set "NPM_CMD=%%N"
    exit /b 0
  )
)
if exist "%ProgramFiles%\nodejs\npm.cmd" (
  set "NPM_CMD=%ProgramFiles%\nodejs\npm.cmd"
  exit /b 0
)
if exist "%LocalAppData%\Programs\nodejs\npm.cmd" (
  set "NPM_CMD=%LocalAppData%\Programs\nodejs\npm.cmd"
  exit /b 0
)
exit /b 0

:install_with_winget
where winget >nul 2>nul
if errorlevel 1 exit /b 0
echo.
echo Trying to install %~2 automatically with winget...
winget install -e --id %~1 --accept-package-agreements --accept-source-agreements
exit /b 0

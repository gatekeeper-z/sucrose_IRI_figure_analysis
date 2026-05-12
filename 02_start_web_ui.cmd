@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================================
echo  IRI Analyzer - start Web UI
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
  set "PY_EXE=%CD%\.venv\Scripts\python.exe"
) else (
  where python >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=python"
  ) else (
    echo Python environment was not found.
    echo Please run 01_setup_environment.cmd first.
    pause
    exit /b 1
  )
)

"%PY_EXE%" -c "import iri_analyzer, fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
  echo Required Python packages are missing.
  echo Please run 01_setup_environment.cmd first.
  pause
  exit /b 1
)

if not exist "web\dist\index.html" (
  echo Frontend build was not found.
  echo Please run 01_setup_environment.cmd first.
  pause
  exit /b 1
)

echo Starting local Web service...
echo URL: http://127.0.0.1:8000
echo.
echo Keep this window open while using the Web UI.
echo Press Ctrl+C in this window to stop the service.
echo.

set "IRI_ANALYZER_NO_AUTO_OPEN=1"
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000'"
"%PY_EXE%" -m iri_analyzer.web

echo.
echo Web service stopped.
pause

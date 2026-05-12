@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0" || (
  echo Failed to enter project directory: %~dp0
  pause
  exit /b 1
)

if not exist "%~dp0scripts\setup_windows.ps1" (
  echo Missing setup script: %~dp0scripts\setup_windows.ps1
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_windows.ps1"
set "SETUP_EXIT=%ERRORLEVEL%"

echo.
if not "%SETUP_EXIT%"=="0" (
  echo Setup failed. Please review the messages above.
)
pause
exit /b %SETUP_EXIT%

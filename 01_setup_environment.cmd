@echo off
setlocal EnableExtensions
chcp 65001 >nul

if exist "%LOCALAPPDATA%\Microsoft\WindowsApps" (
  set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"
)

if /I not "%~1"=="__inner" (
  start "IRI Analyzer Setup" "%ComSpec%" /k ""%~f0" __inner"
  exit /b
)

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
echo.
echo This setup window will stay open. You can close it manually after reading the output.
exit /b %SETUP_EXIT%

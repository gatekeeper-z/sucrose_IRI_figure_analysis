@echo off
setlocal EnableExtensions
chcp 65001 >nul
title IRI Analyzer Setup

set "ROOT_DIR=%~dp0"
set "SETUP_SCRIPT=%ROOT_DIR%scripts\setup_windows.ps1"
set "LAUNCH_LOG=%ROOT_DIR%setup_launcher.log"
set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS_EXE%" set "PS_EXE=powershell.exe"

echo IRI Analyzer setup launcher > "%LAUNCH_LOG%"
echo Started: %DATE% %TIME% >> "%LAUNCH_LOG%"
echo Root: %ROOT_DIR% >> "%LAUNCH_LOG%"
echo PowerShell: %PS_EXE% >> "%LAUNCH_LOG%"
echo Initial PATH: %PATH% >> "%LAUNCH_LOG%"

echo.
echo ============================================================
echo  IRI Analyzer - environment setup launcher
echo ============================================================
echo Project directory:
echo %ROOT_DIR%
echo.
echo Launcher log:
echo %LAUNCH_LOG%
echo.

cd /d "%ROOT_DIR%"
if errorlevel 1 (
  echo Failed to enter project directory: %ROOT_DIR%
  echo Failed to enter project directory. >> "%LAUNCH_LOG%"
  goto finish_fail
)

if not exist "%SETUP_SCRIPT%" (
  echo Missing setup script:
  echo %SETUP_SCRIPT%
  echo Missing setup script: %SETUP_SCRIPT% >> "%LAUNCH_LOG%"
  goto finish_fail
)

set "BOOTSTRAP_PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\WindowsPowerShell\v1.0"
if defined LOCALAPPDATA set "BOOTSTRAP_PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%BOOTSTRAP_PATH%"
if defined USERPROFILE set "BOOTSTRAP_PATH=%USERPROFILE%\AppData\Local\Microsoft\WindowsApps;%BOOTSTRAP_PATH%"
set "PATH=%BOOTSTRAP_PATH%;%PATH%"
echo Bootstrap PATH prefix: %BOOTSTRAP_PATH% >> "%LAUNCH_LOG%"
echo PATH after bootstrap: %PATH% >> "%LAUNCH_LOG%"
echo where winget result: >> "%LAUNCH_LOG%"
where winget >> "%LAUNCH_LOG%" 2>&1
echo winget --version result: >> "%LAUNCH_LOG%"
winget --version >> "%LAUNCH_LOG%" 2>&1

echo Running Windows setup script...
echo Running setup script: %SETUP_SCRIPT% >> "%LAUNCH_LOG%"
echo.
"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SETUP_SCRIPT%"
set "SETUP_EXIT=%ERRORLEVEL%"
echo Setup script exit code: %SETUP_EXIT% >> "%LAUNCH_LOG%"

echo.
if "%SETUP_EXIT%"=="0" (
  echo Setup complete. You can now double-click 02_start_web_ui.cmd
) else (
  echo Setup failed. Please review the messages above.
  echo.
  echo If the error is not clear, send these files for diagnosis:
  echo %LAUNCH_LOG%
  echo %ROOT_DIR%setup_windows.log
)
goto finish

:finish_fail
set "SETUP_EXIT=1"

:finish
echo.
echo This window will stay open. You can close it manually after reading the output.
pause
exit /b %SETUP_EXIT%

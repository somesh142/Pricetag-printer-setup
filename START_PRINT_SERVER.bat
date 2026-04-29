@echo off
title Price Tag Print Server — Sri Murugan Trading
color 0A
echo.
echo  ==========================================
echo   Price Tag Print Server
echo   Sri Murugan Trading - AUS
echo   Engine: Python (win32print RAW)
echo  ==========================================
echo.

REM Check Python is installed
python --version >nul 2>&1
IF ERRORLEVEL 1 (
  color 0C
  echo  ERROR: Python is not installed!
  echo.
  echo  Please download and install Python from:
  echo  https://www.python.org/downloads/
  echo.
  echo  IMPORTANT: Tick "Add Python to PATH" during install!
  echo.
  pause
  exit /b 1
)

echo  Python found. Starting print server...
echo  (pywin32 will auto-install on first run)
echo.
python "%~dp0print_server.py"
pause

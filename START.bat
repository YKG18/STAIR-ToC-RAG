@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Installing Python 3.12...
  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
  echo Python installed. Please double-click START.bat again.
  pause
  exit /b
)
python launcher.py

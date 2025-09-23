@echo off
:: Windows 11 System Monitor Launcher
:: This batch file launches the system monitor application

:: Change to the script directory
cd /d "%~dp0"

:: Check if Python virtual environment exists, create if not
if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python environment for first time use...
    echo This may take a minute...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip install -r requirements.txt
    echo Environment setup complete.
)

:: Run the Python launcher script with the virtual environment
echo Starting Windows 11 System Monitor...
start "" /b ".venv\Scripts\pythonw.exe" launcher.py

:: Exit silently - The application runs in the system tray
exit
pause

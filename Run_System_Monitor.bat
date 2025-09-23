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
) else (
    :: Make sure all dependencies are installed correctly
    echo Checking and updating dependencies...
    .venv\Scripts\pip install -r requirements.txt --quiet
)

:: Run the Python launcher script with the virtual environment
echo Starting Windows 11 System Monitor...
start "" /b ".venv\Scripts\pythonw.exe" launcher.py 2>error.log

:: Check if there was an error launching
timeout /t 2 > nul
if exist error.log (
    if %ERRORLEVEL% NEQ 0 (
        echo Error detected while starting. See error.log for details.
        pause
    )
)

:: Exit silently - The application runs in the system tray
exit
@echo off
echo ============================================================
echo   RF-IDS  ^|  RF Intrusion Detection System
echo   Starting Backend Server...
echo ============================================================
echo.

cd /d "%~dp0backend"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.10+
    pause
    exit /b 1
)

:: Install dependencies if needed
if not exist ".deps_installed" (
    echo [SETUP] Installing Python dependencies...
    pip install -r ..\requirements.txt
    echo. > .deps_installed
)

echo [INFO] Starting Flask + SocketIO server on http://localhost:5000
echo [INFO] Open frontend\index.html in your browser
echo [INFO] Press Ctrl+C to stop
echo.

python server.py
pause

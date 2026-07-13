@echo off
title HXL Ontology Tagger

echo.
echo  ============================================
echo   HXL Ontology Tagger - Starting...
echo  ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Install Python 3.9+ from https://python.org
    echo  IMPORTANT: tick "Add to PATH" during install.
    pause
    exit /b 1
)

if not exist ".deps_ok" (
    echo  Installing packages (first run only, ~30 seconds)...
    pip install -r requirements.txt --quiet
    echo. > .deps_ok
    echo  Done.
    echo.
)

if not exist ".env" (
    echo  NOTE: No .env file found.
    echo  Copy .env.example to .env and add your API key,
    echo  or use the Settings button inside the app.
    echo.
)

echo  Starting at http://localhost:8000
echo  Press Ctrl+C to stop.
echo.

start /B cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"
python app.py
pause

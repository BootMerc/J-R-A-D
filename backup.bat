@echo off
setlocal

if not exist venv (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python scripts\backup.py
if errorlevel 1 (
    pause
    exit /b 1
)

pause

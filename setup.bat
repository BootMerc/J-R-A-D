@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  Recruitment Automation Dashboard - Setup
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    echo         and make sure "Add python.exe to PATH" is checked during install.
    pause
    exit /b 1
)

python --version

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
) else (
    echo Virtual environment already exists, skipping creation.
)

call venv\Scripts\activate.bat

echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed. See the output above.
    pause
    exit /b 1
)

if not exist .env (
    echo Creating .env from .env.example...
    copy .env.example .env >nul
) else (
    echo .env already exists, leaving it untouched.
)

if not exist data mkdir data
if not exist logs mkdir logs
if not exist backups mkdir backups

echo Initializing database...
python -c "from app.database.database import init_db; init_db(); print('Database ready at data\\recruitment.db')"

echo.
echo ============================================
echo  Setup complete. Run run.bat to start the app.
echo ============================================
pause

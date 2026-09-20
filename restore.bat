@echo off
setlocal

if not exist venv (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

echo ============================================
echo  IMPORTANT: close run.bat's two windows
echo  (or Ctrl+C inside them) before restoring.
echo  Restoring while the app is running can
echo  leave the database in an inconsistent state.
echo ============================================
echo.

call venv\Scripts\activate.bat
python scripts\restore.py %*
if errorlevel 1 (
    pause
    exit /b 1
)

pause

@echo off
setlocal

if not exist venv (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

echo Starting FastAPI backend on http://127.0.0.1:8000 ...
start "Recruitment Dashboard - API" cmd /k "call venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo Starting Streamlit frontend on http://127.0.0.1:8501 ...
start "Recruitment Dashboard - UI" cmd /k "call venv\Scripts\activate.bat && streamlit run frontend\dashboard.py --server.port 8501"

timeout /t 3 /nobreak >nul
start http://127.0.0.1:8501

echo.
echo Both servers are starting in separate windows.
echo Close those windows (or press Ctrl+C inside them) to stop the app.

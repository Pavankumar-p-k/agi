@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   JARVIS AI OS - ENVIRONMENT SETUP
echo ============================================================

REM Check Python Installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.11+ and add it to PATH.
    pause
    exit /b 1
)

REM Create Virtual Environment
if not exist "venv" (
    echo [1/3] Creating Virtual Environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
) else (
    echo [OK] Virtual Environment already exists.
)

REM Install Dependencies
echo [2/3] Installing/Updating dependencies...
call venv\Scripts\activate
pip install --upgrade pip
pip install -e .
if !errorlevel! neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

REM Initialize Database
echo [3/3] Initializing Database...
python -c "from core.database import init_db; import asyncio; asyncio.run(init_db())"
if !errorlevel! neq 0 (
    echo [WARNING] Database init failed or already exists. Continuing...
)

echo.
echo ============================================================
echo   SETUP COMPLETE! Run 'start.bat' to launch JARVIS.
echo ============================================================
pause

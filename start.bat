@echo off
title JARVIS Startup
echo ========================================
echo        JARVIS - Starting All Services
echo ========================================
echo.

:: Check if Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running! Please start Docker Desktop first.
    pause
    exit /b 1
)
echo [OK] Docker is running.

:: Start Docker containers (if not already running)
echo.
echo [1/4] Starting Docker services...
docker start jarvis-n8n 2>nul || docker run -d --name jarvis-n8n --restart unless-stopped -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n:latest
echo   - n8n: http://localhost:5678

docker start searxng 2>nul || docker run -d --name searxng --restart unless-stopped -p 8888:8080 -v searxng_data:/etc/searxng searxng/searxng:latest
echo   - SearXNG: http://localhost:8888

:: Start Ollama
echo.
echo [2/4] Starting Ollama...
tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if %errorlevel% neq 0 (
    start /B "" "C:\Users\peter\AppData\Local\Programs\Ollama\ollama.exe" serve
    echo   Waiting for Ollama to initialize...
    timeout /t 5 /nobreak >nul
    echo   [OK] Ollama started
) else (
    echo   [OK] Ollama already running
)

:: Start JARVIS server
echo.
echo [3/4] Starting JARVIS server (port 8000)...
start /B "" "cmd /c python -m core.main > jarvis_server.log 2>&1"
echo   Server starting... (check jarvis_server.log for status)
echo   This takes ~50s due to litellm imports.
echo.
echo [4/4] Opening Dashboard...
timeout /t 10 /nobreak >nul
start "" http://localhost:8000
echo.
echo ========================================
echo   JARVIS is starting up!
echo   - Dashboard:  http://localhost:8000
echo   - n8n:        http://localhost:5678
echo   - SearXNG:    http://localhost:8888
echo   - Log:        jarvis_server.log
echo ========================================
echo.
echo Press any key to view server log, or close this window.
pause >nul
type jarvis_server.log
echo.
echo Server is running. Close this window when done.
pause

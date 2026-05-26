@echo off
title JARVIS Docker Restart
echo ========================================
echo   Restarting JARVIS Docker Containers
echo ========================================
echo.

:: Check if Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running! Please start Docker Desktop first.
    echo   Tip: Add Docker Desktop to Windows startup (Settings ^> General ^> Start Docker when you log in)
    pause
    exit /b 1
)
echo [OK] Docker is running.

echo Waiting for Docker to initialize...
timeout /t 5 /nobreak >nul

echo [1/2] Restarting SearXNG (port 8888)...
docker start searxng 2>nul || docker run -d --name searxng --restart unless-stopped -p 8888:8080 -v searxng_data:/etc/searxng searxng/searxng:latest
if %errorlevel% equ 0 ( echo   [OK] SearXNG started ) else ( echo   [FAIL] Could not start SearXNG )

echo [2/2] Restarting n8n (port 5678)...
docker start jarvis-n8n 2>nul || docker run -d --name jarvis-n8n --restart unless-stopped -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n:latest
if %errorlevel% equ 0 ( echo   [OK] n8n started ) else ( echo   [FAIL] Could not start n8n )

echo.
echo ========================================
echo   Done! Verify at:
echo   - SearXNG: http://localhost:8888
echo   - n8n:     http://localhost:5678
echo ========================================
echo.
pause

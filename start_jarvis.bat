@echo off
setlocal

set "ROOT=%~dp0"
set "MODEL=%~1"
if "%MODEL%"=="" set "MODEL=llama3.1:latest"

set "OLLAMA_URL=http://127.0.0.1:11434"
set "OLLAMA_MODEL=%MODEL%"
set "API_BASE_URL=http://127.0.0.1:8000"
set "WS_URL=ws://127.0.0.1:8000/ws"

echo.
echo Starting JARVIS with model: %OLLAMA_MODEL%
echo Backend: %API_BASE_URL%
echo WebSocket: %WS_URL%
echo.

start "Ollama" ollama serve
timeout /t 2 >nul

start "JARVIS Backend" /D "%ROOT%" "%ROOT%.venv311\Scripts\python.exe" -m core.main
if errorlevel 1 start "JARVIS Backend" /D "%ROOT%" "%ROOT%.venv\Scripts\python.exe" -m core.main
if errorlevel 1 start "JARVIS Backend" /D "%ROOT%" python -m core.main
timeout /t 2 >nul

if exist "%ROOT%apps\jarvis_app\pubspec.yaml" (
    start "JARVIS GUI" /D "%ROOT%apps\jarvis_app" flutter run -d windows --dart-define=API_BASE_URL=%API_BASE_URL% --dart-define=WS_URL=%WS_URL%
) else (
    echo WARNING: Flutter app not found at %ROOT%apps\jarvis_app - skipping GUI
)

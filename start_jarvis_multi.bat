@echo off
setlocal

set "ROOT=%~dp0"

REM Multi-instance routing map (model -> port)
set "OLLAMA_MODEL_ENDPOINTS=tinyllama=http://127.0.0.1:11434;deepseek-r1:1.5b=http://127.0.0.1:11435;qwen2.5-coder:3b=http://127.0.0.1:11436;qwen3:4b=http://127.0.0.1:11437;qwen2.5:7b=http://127.0.0.1:11438;mistral:7b=http://127.0.0.1:11439;llama3.1:8b=http://127.0.0.1:11440;phi3:mini=http://127.0.0.1:11441;moondream=http://127.0.0.1:11442"
set "OLLAMA_MULTI_INSTANCE=1"

REM Common Ollama env (tune if needed)
set "OLLAMA_NUM_GPU=99"
set "OLLAMA_KEEP_ALIVE=300"
set "OLLAMA_NUM_PARALLEL=1"
set "OLLAMA_FLASH_ATTENTION=1"
set "OLLAMA_KV_CACHE_TYPE=q8_0"
set "OLLAMA_MAX_LOADED_MODELS=1"
set "CUDA_VISIBLE_DEVICES=0"

set "API_BASE_URL=http://127.0.0.1:8000"
set "WS_URL=ws://127.0.0.1:8000/ws"

echo.
echo Starting multi-instance Ollama servers...
call :start_ollama "tinyllama" "11434"
call :start_ollama "deepseek-r1:1.5b" "11435"
call :start_ollama "qwen2.5-coder:3b" "11436"
call :start_ollama "qwen3:4b" "11437"
call :start_ollama "qwen2.5:7b" "11438"
call :start_ollama "mistral:7b" "11439"
call :start_ollama "llama3.1:8b" "11440"
call :start_ollama "phi3:mini" "11441"
call :start_ollama "moondream" "11442"

timeout /t 2 >nul

echo.
echo Starting JARVIS backend...
start "JARVIS Backend" /D "%ROOT%backend" "%ROOT%backend\.venv311\Scripts\python.exe" -m core.main
timeout /t 2 >nul

echo.
echo Starting JARVIS GUI...
start "JARVIS GUI" /D "%ROOT%apps\jarvis_app" flutter run -d windows --dart-define=API_BASE_URL=%API_BASE_URL% --dart-define=WS_URL=%WS_URL%
exit /b 0

:start_ollama
set "MODEL=%~1"
set "PORT=%~2"
start "Ollama-%MODEL%" cmd /c "set OLLAMA_HOST=127.0.0.1:%PORT% ^&^& set OLLAMA_NUM_GPU=%OLLAMA_NUM_GPU% ^&^& set OLLAMA_KEEP_ALIVE=%OLLAMA_KEEP_ALIVE% ^&^& set OLLAMA_NUM_PARALLEL=%OLLAMA_NUM_PARALLEL% ^&^& set OLLAMA_FLASH_ATTENTION=%OLLAMA_FLASH_ATTENTION% ^&^& set OLLAMA_KV_CACHE_TYPE=%OLLAMA_KV_CACHE_TYPE% ^&^& set OLLAMA_MAX_LOADED_MODELS=%OLLAMA_MAX_LOADED_MODELS% ^&^& set CUDA_VISIBLE_DEVICES=%CUDA_VISIBLE_DEVICES% ^&^& ollama serve"
exit /b 0

@echo off
echo ================================================
echo   JARVIS - NVIDIA Free API Setup
echo ================================================
echo.
echo This script will help you set up NVIDIA NIM free API access.
echo.
echo Steps:
echo 1. Get your free API key from: https://build.nvidia.com/settings/api-keys
echo    (Login with your email - no phone verification needed for basic access)
echo.
echo 2. Once you have your API key, run:
echo    setx NGC_API_KEY "your-api-key-here"
echo.
echo 3. Then configure JARVIS to use NVIDIA models:
echo    setx JARVIS_MODEL_API_BASE_URL "https://integrate.api.nvidia.com/v1"
echo    setx JARVIS_MODEL_PROVIDER "rest"
echo.
echo 4. Test with:
echo    python -m jarvis_os "test NVIDIA API"
echo.
echo ================================================
echo.
echo NVIDIA Free Models Available:
echo  - mistral-7b-instruct (free tier)
echo  - llama-3.1-8b-instruct (free tier)
echo  - gpt-oss-20b (OpenAI model via NVIDIA)
echo  - nemotron-3-nano-omni-30b (multimodal)
echo  - And many more at: https://build.nvidia.com/models
echo.
echo Press any key to open the NVIDIA API keys page...
pause >nul
start https://build.nvidia.com/settings/api-keys

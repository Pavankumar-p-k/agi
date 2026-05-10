# NVIDIA Free API Setup for JARVIS

## Quick Start

### 1. Get Your Free API Key

1. Visit: https://build.nvidia.com/settings/api-keys
2. Sign in with your email (no phone verification required for basic access)
3. Click "Generate Personal Key"
4. Copy your API key

### 2. Configure Environment

Run these commands in PowerShell:

```powershell
# Set your NVIDIA API key
[System.Environment]::SetEnvironmentVariable("NGC_API_KEY", "your-api-key-here", "User")

# Set JARVIS to use NVIDIA API
[System.Environment]::SetEnvironmentVariable("JARVIS_MODEL_API_BASE_URL", "https://integrate.api.nvidia.com/v1", "User")
[System.Environment]::SetEnvironmentVariable("JARVIS_MODEL_PROVIDER", "rest", "User")
```

Or use the batch file:
```cmd
setup_nvidia_api.bat
```

### 3. Test NVIDIA API

```bash
# Test with a simple prompt
python -m jarvis_os "What is 2+2?"

# Check status
python -m jarvis_os --status

# List available models (via NVIDIA)
curl -H "Authorization: Bearer $NGC_API_KEY" https://integrate.api.nvidia.com/v1/models
```

## NVIDIA Free Models

| Model | Description | Access |
|-------|-------------|--------|
| `mistral-7b-instruct` | Fast, efficient 7B model | Free tier |
| `llama-3.1-8b-instruct` | Meta's 8B instruct model | Free tier |
| `gpt-oss-20b` | OpenAI-compatible 20B model | Free tier |
| `nemotron-3-nano-omni-30b` | NVIDIA's multimodal 30B | Free tier |
| `qwen3-4b` | Alibaba's 4B model | Free tier |

Full catalog: https://build.nvidia.com/models

## Using NVIDIA Models in JARVIS

### Option 1: Environment Variables (Recommended)

```powershell
# Set default model to use
[System.Environment]::SetEnvironmentVariable("JARVIS_DEFAULT_CHAT_MODEL", "llama-3.1-8b-instruct", "User")
[System.Environment]::SetEnvironmentVariable("JARVIS_DEFAULT_REASONING_MODEL", "nemotron-3-nano-omni-30b", "User")
```

### Option 2: Test with Ollama (Your Local Models)

You already have Ollama running locally with these models:
- `mistral:latest` (4.4 GB)
- `tinyllama:latest` (637 MB)
- `llama3.1:latest` (4.9 GB)
- `qwen2.5-coder:3b` (1.9 GB)
- And more...

JARVIS will use Ollama by default. To switch to NVIDIA API:

```bash
# In PowerShell
$env:JARVIS_MODEL_PROVIDER = "rest"
$env:JARVIS_MODEL_API_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Run JARVIS with NVIDIA
python -m jarvis_os "your prompt here"
```

## Troubleshooting

### Issue: "Application Error" on build.nvidia.com
**Solution:** Try a different browser or incognito mode. Some users report issues with Chrome.

### Issue: Phone verification problem
**Solution:** Use email-only signup. NVIDIA usually doesn't require phone verification for basic free tier.

### Issue: API key not working
**Solution:** Make sure you set the environment variable correctly:
```powershell
# Verify
echo $env:NGC_API_KEY
```

## JARVIS + NVIDIA + Ollama = Best of Both Worlds

- **Ollama (Local):** Fast, private, no internet needed
- **NVIDIA API (Cloud):** Powerful models, free tier, no GPU needed

JARVIS automatically routes between them based on task!

## Next Steps

1. Get your NVIDIA API key
2. Run `setup_nvidia_api.bat`
3. Test: `python -m jarvis_os "Hello from NVIDIA!"`
4. Compare with local: `python -m jarvis_os --model-provider ollama "Hello from local!"`

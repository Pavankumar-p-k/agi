"""core/llm_router.py
LiteLLM Router — unified API for all LLM calls with auto-failover.
"""
import os
from litellm import Router

MODEL_LIST = [
    {"model_name": "chat", "litellm_params": {"model": "ollama/llama3.1:8b", "api_base": "http://localhost:11434", "max_tokens": 4096, "temperature": 0.7}},
    {"model_name": "code", "litellm_params": {"model": "ollama/qwen2.5-coder:3b", "api_base": "http://localhost:11434", "max_tokens": 4096, "temperature": 0.3}},
    {"model_name": "analysis", "litellm_params": {"model": "ollama/qwen2.5:7b", "api_base": "http://localhost:11434", "max_tokens": 4096, "temperature": 0.5}},
    {"model_name": "reasoning", "litellm_params": {"model": "ollama/deepseek-r1:1.5b", "api_base": "http://localhost:11434", "max_tokens": 4096, "temperature": 0.6}},
    {"model_name": "creative", "litellm_params": {"model": "ollama/mistral:7b", "api_base": "http://localhost:11434", "max_tokens": 4096, "temperature": 0.8}},
    {"model_name": "vision", "litellm_params": {"model": "ollama/moondream", "api_base": "http://localhost:11434", "max_tokens": 2048}},
    {"model_name": "fast", "litellm_params": {"model": "ollama/tinyllama", "api_base": "http://localhost:11434", "max_tokens": 2048, "temperature": 0.3}},
    {"model_name": "automation", "litellm_params": {"model": "ollama/qwen3:4b", "api_base": "http://localhost:11434", "max_tokens": 4096, "temperature": 0.3}},
]

CLOUD_MODELS = []
for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
    if os.getenv(key):
        CLOUD_MODELS.append(key)
if os.getenv("ANTHROPIC_API_KEY"):
    MODEL_LIST.append({"model_name": "cloud", "litellm_params": {"model": "claude-sonnet-4-20250514", "api_key": os.getenv("ANTHROPIC_API_KEY"), "max_tokens": 8192}})
    MODEL_LIST.append({"model_name": "cloud", "litellm_params": {"model": "claude-haiku-3-5-20241022", "api_key": os.getenv("ANTHROPIC_API_KEY"), "max_tokens": 8192}})
if os.getenv("OPENAI_API_KEY"):
    MODEL_LIST.append({"model_name": "cloud", "litellm_params": {"model": "gpt-4o", "api_key": os.getenv("OPENAI_API_KEY"), "max_tokens": 8192}})
    MODEL_LIST.append({"model_name": "cloud", "litellm_params": {"model": "gpt-4o-mini", "api_key": os.getenv("OPENAI_API_KEY"), "max_tokens": 8192}})
if os.getenv("GEMINI_API_KEY"):
    MODEL_LIST.append({"model_name": "cloud", "litellm_params": {"model": "gemini/gemini-2.5-flash", "api_key": os.getenv("GEMINI_API_KEY"), "max_tokens": 8192}})
if os.getenv("GROQ_API_KEY"):
    MODEL_LIST.append({"model_name": "cloud", "litellm_params": {"model": "groq/llama-3.3-70b-versatile", "api_key": os.getenv("GROQ_API_KEY"), "max_tokens": 8192, "temperature": 0.7}})
    MODEL_LIST.append({"model_name": "cloud", "litellm_params": {"model": "groq/llama-3.1-8b-instant", "api_key": os.getenv("GROQ_API_KEY"), "max_tokens": 4096, "temperature": 0.3}})

router = Router(model_list=MODEL_LIST)


def get_available_cloud_providers() -> list:
    providers = []
    if os.getenv("ANTHROPIC_API_KEY"):
        providers.append("claude")
    if os.getenv("OPENAI_API_KEY"):
        providers.append("openai")
    if os.getenv("GEMINI_API_KEY"):
        providers.append("gemini")
    return providers


async def complete(model_group: str, messages: list, timeout: int = 120) -> str:
    response = await router.acompletion(
        model=model_group,
        messages=messages,
        timeout=timeout,
    )
    return response.choices[0].message.content


async def health_check() -> bool:
    try:
        await router.acompletion(
            model="fast",
            messages=[{"role": "user", "content": "ping"}],
            timeout=5,
        )
        return True
    except Exception:
        return False

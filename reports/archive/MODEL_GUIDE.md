# Model Guide — JARVIS Model Providers

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  ModelRouter                      │
│  selects provider based on task, latency, cost    │
│  availability, user preference                    │
├──────────────────────────────────────────────────┤
│  Task Profiles:                                   │
│  coding:   primary=local,  fallback=cloud         │
│  vision:   primary=local,  fallback=cloud         │
│  planning: primary=local,  fallback=cloud         │
│  chat:     primary=local,  fallback=cloud         │
└──────┬───────────────────────┬───────────────────┘
       │                       │
┌──────▼──────┐         ┌──────▼──────┐
│ Local        │         │ Cloud        │
│ Providers    │         │ Providers    │
├──────────────┤         ├──────────────┤
│ Ollama       │         │ OpenAI       │
│              │         │ Anthropic    │
│              │         │ Gemini       │
│              │         │ Groq         │
│              │         │ OpenRouter   │
└──────────────┘         └──────────────┘
```

## Available Providers

| Provider | Class | Default Model | Requires |
|----------|-------|--------------|----------|
| Ollama | `OllamaProvider` | `qwen2.5-coder:3b` | Ollama running locally |
| OpenAI | `OpenAIProvider` | `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `AnthropicProvider` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| Gemini | `GeminiProvider` | `gemini-2.0-flash` | `GEMINI_API_KEY` |
| Groq | `GroqProvider` | `llama3-70b-8192` | `GROQ_API_KEY` |
| OpenRouter | `OpenRouterProvider` | `openai/gpt-4o` | `OPENROUTER_API_KEY` |

## API

```python
from core.model_providers import get_router
router = get_router()

# Generate
result = await router.generate(task, messages)

# Stream
async for chunk in router.stream(task, messages):
    print(chunk)

# Embeddings
emb = await router.embeddings(task, "text")

# Vision
result = await router.vision(task, messages, image_base64)

# Health check
health = await router.health_check()
```

## Runtime Switching

Switch providers at runtime from any interface:

**CLI:**
```
jarvis settings set task_profile.coding primary=openai
jarvis settings set task_profile.coding fallback=anthropic
```

**Slash command:**
```
/models switch coding openai
```

**config.yaml:**
```yaml
task_profiles:
  coding:
    primary: openai
    fallback: anthropic
  vision:
    primary: local
    fallback: openai
```

**No code edits required** — all routing is config-driven via `core.config_registry`.

## Task Profiles

| Task Type | Default Primary | Default Fallback |
|-----------|----------------|------------------|
| chat | local | cloud |
| coding | local | cloud |
| vision | local | cloud |
| planning | local | cloud |
| analysis | local | cloud |
| reasoning | local | cloud |
| embeddings | local | cloud |
| classifier | local | cloud |
| creative | local | cloud |
| grader | local | cloud |

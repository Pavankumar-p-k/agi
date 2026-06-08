# JARVIS Cookbook

Example workflows for common tasks. Copy, paste, and adapt.

## Research a topic with parallel agents

```bash
jarvis nexus "summarize the top 5 AI papers this month"
jarvis atlas "find the latest research on multimodal LLMs"
```

## Code review + fix in one go

```bash
jarvis forge "review src/main.py for bugs and security issues"
```

## Voice-controlled PC automation

```bash
jarvis server
# Then speak: "open Chrome, search for JARVIS AI, and summarize the first result"
```

## Monitor system health

```bash
jarvis doctor --json
```

## Create a custom skill

Run this inside a JARVIS chat:
<pre>
```create_skill
{
  "name": "greet-user",
  "triggers": ["hello", "hi", "good morning"],
  "description": "Greets the user warmly",
  "handler_code": "async def handle(message): return f'Hello there! You said: {message}'"
}
```
</pre>

## Multi-model comparison

```bash
jarvis cli
# Then in chat: ask a question, then use chat_with_model to ask the same question
# to a different model for comparison
```

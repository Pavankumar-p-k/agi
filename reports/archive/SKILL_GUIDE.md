# Skill Guide — JARVIS Skill Platform

## Architecture

JARVIS has three skill systems that work together:

1. **Trigger-based skills** — `skills/{name}.md` + `skills/{name}.py`, loaded by `core/skill_loader.py`
2. **Registry-based skills** — Learned procedures stored in `data/skills.json`, managed via `services/memory/skills.py`
3. **Package skills** — `skills/installed/{name}/skill.json`, loaded by `skills/manager.py`

## Creating a Skill

### Via CLI
```bash
jarvis skill create weather
```

This generates:
```
skills/weather.md          # Trigger definition
skills/weather.py          # Handler implementation
tests/test_weather.py      # Test file
```

### SKILL.md Format
```yaml
---
name: weather
description: "Get weather forecasts"
triggers:
  - "weather"
  - "forecast"
  - "temperature"
---

# weather

Skill description and usage notes.
```

### Handler Format (`skills/weather.py`)
```python
async def handle(message: str) -> str:
    return f"{message} (handled by weather skill)"
```

### Via Agent Tool
While chatting with JARVIS, use the `create_skill` tool:
```
User: Create a skill that checks my calendar
JARVIS: Created calendar skill with triggers ["calendar", "schedule"]
```

## Registry Skills (Learned Procedures)

JARVIS can learn skills from experience. Use the `manage_skills` tool:
- `list` — Show all learned skills
- `view` — Show skill details
- `add` — Create a learned procedure
- `search` — Find relevant skills
- `delete` — Remove a skill

## Auto-Discovery

Skills in the `skills/` directory are auto-discovered at startup. Trigger-based matching uses substring matching against user messages.

## Listing Installed Skills

```bash
jarvis skill list
```

Output:
```
┌──────────┬──────────────────┬──────────────────┐
│ Name     │ Description      │ Triggers         │
├──────────┼──────────────────┼──────────────────┤
│ weather  │ Get forecasts    │ weather forecast │
│ email    │ Send emails      │ email compose    │
└──────────┴──────────────────┴──────────────────┘
```

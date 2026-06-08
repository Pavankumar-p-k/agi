# Plugin SDK

JARVIS supports third-party plugins with hot-reload, hooks, and dependency management.

## Quick Start

```python
from jarvis_plugin_sdk import Plugin, hook

class MyPlugin(Plugin):
    @hook("before_agent_run")
    async def on_before_run(self, task: str) -> bool:
        if "block" in task:
            return False
        return True
```

## Plugin Structure

```
my_plugin/
├── plugin.yaml       # Manifest
├── __init__.py       # Entry point
└── requirements.txt  # Dependencies
```

## Manifest (`plugin.yaml`)

```yaml
name: my-plugin
version: 1.0.0
description: Does something useful
entrypoint: __init__.py
hooks:
  - before_agent_run
  - agent_end
```

## Available Hooks

| Hook | Signature | Description |
|------|-----------|-------------|
| `before_agent_run` | `(task: str) -> bool` | Return False to block execution |
| `agent_end` | `(result: dict) -> None` | Called after agent completes |
| `on_message` | `(message: str) -> str` | Transform incoming messages |
| `on_response` | `(response: str) -> str` | Transform outgoing responses |

## Loading

Place plugins in the `plugins/` directory. They are loaded automatically at startup with hot-reload via watchdog.

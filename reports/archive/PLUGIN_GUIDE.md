# Plugin Guide — JARVIS Plugin Platform

## Architecture

The plugin system lives in `core/plugins/` with 22 files providing a complete plugin framework.

## Creating a Plugin

### Via CLI
```bash
jarvis plugin create my-plugin
```

This creates:
```
plugins/my-plugin/
├── plugin.json         # Manifest
└── my_plugin.py        # Implementation
```

### Via Manual Setup

1. Create a directory under `plugins/`:
```
plugins/my-plugin/
├── plugin.json
└── main.py
```

2. **plugin.json:**
```json
{
  "name": "jarvis.my-plugin",
  "version": "1.0.0",
  "description": "My custom plugin",
  "author": "You",
  "entry_point": "main.py",
  "enabled": true,
  "hooks": ["on_load", "on_unload"]
}
```

3. **main.py:**
```python
from core.plugins.base import Plugin

class MyPlugin(Plugin):
    def on_load(self):
        self.register_tool("my_tool", self.handle_my_tool)

    async def handle_my_tool(self, args):
        return {"result": "done"}
```

## Available Hooks

| Hook | Description |
|------|-------------|
| `on_load` | Called when plugin is loaded |
| `on_unload` | Called when plugin is unloaded |
| `on_execute` | Before tool execution |
| `on_governance_check` | Before governance approval |
| `on_routing_decision` | Before model routing |
| `on_redact` | Before content is sent to LLM |
| `before_model_resolve` | Before model name resolution |
| `llm_input` | Before LLM call |
| `llm_output` | After LLM response |
| `on_stt` | After speech-to-text |
| `on_wake_word` | On wake word detection |

## Plugin Lifecycle

1. `on_load` — Plugin registers hooks and tools
2. Active — Plugin intercepts relevant events
3. `on_unload` — Plugin cleans up resources

## Hot Reload

Plugins in the `plugins/` directory are watched for changes. Update a file and it reloads automatically.

```bash
jarvis plugin reload jarvis.my-plugin
```

## Sandboxing

Plugins run with import sandboxing via AST analysis. The sandbox blocks dangerous imports (`subprocess`, `os.system`, `shutil.rmtree`, etc.) unless explicitly allowed.

## Marketplace

```bash
jarvis plugin search my-plugin
jarvis plugin install jarvis-my-plugin
```

Plugins are published via PyPI with `jarvis-plugin-` prefix.

## Versioning

- `compatibility.py` enforces version constraints
- `requires` field in manifest declares minimum JARVIS version

# Provider SDK — Create a Provider

> **Audience:** Developers extending JARVIS with new capabilities.
> **Time:** ~15 minutes to create and register a working provider.

---

## 1. What Is a Provider?

A provider is a pluggable implementation of a **capability** — coding, browser,
email, deployment, voice, desktop control, etc. JARVIS routes work to providers
based on capability name, historical evidence, health, and cost.

There are **two required parts** to every provider:

| Part | File | Purpose |
|------|------|---------|
| **Manifest** | `provider.yaml` | Declares identity, permissions, transport, dependencies |
| **Adapter** | `adapters/my_provider.py` | Implements the `ExecutionProvider` ABC |

---

## 2. Step-by-Step

### Step 1: Create the manifest

`providers/my_provider/provider.yaml`:

```yaml
# ── Identity ──────────────────────────────────────────────────────
id: "my_provider"
publisher: "your-name"
version: "1.0.0"
name: "My Custom Provider"
description: "Does something useful"

# ── Compatibility ─────────────────────────────────────────────────
sdk_version: 2
api_version: 1
minimum_jarvis: "3.0.0"

# ── Transport ─────────────────────────────────────────────────────
transport: "python"
entrypoint: "adapters/my_provider.py"

# ── Permissions ───────────────────────────────────────────────────
permissions:
  - "filesystem.read"
  - "network.http"

# ── Platforms ─────────────────────────────────────────────────────
platforms:
  - "windows"
  - "linux"
  - "darwin"

# ── Capabilities ──────────────────────────────────────────────────
capabilities:
  - id: "my_capability"
    version: 1

# ── Dependencies ──────────────────────────────────────────────────
dependencies:
  - "httpx>=0.27"
```

See the [full manifest spec](../specs/provider-manifest-v2.md) for all fields.

### Step 2: Write the adapter

`providers/my_provider/adapters/my_provider.py`:

```python
from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class MyProvider(ExecutionProvider):
    provider_id = "my_provider"
    name = "My Custom Provider"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["my_capability"],
            features=["feature_a", "feature_b"],
        )

    async def health(self) -> ProviderHealth:
        try:
            # Check if dependencies are reachable
            return ProviderHealth(
                status=ProviderHealthStatus.HEALTHY,
                latency_ms=0.0,
                last_checked=time.time(),
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error=str(e),
                last_checked=time.time(),
            )

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        start = time.monotonic()
        action = task.get("action", "")

        try:
            if action == "do_something":
                return await self._do_something(task, start)
            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown action: {action}",
                )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    async def _do_something(
        self,
        task: dict[str, Any],
        start: float,
    ) -> ExecutionResult:
        # Your implementation here
        result = task.get("input", "")
        return ExecutionResult(
            success=True,
            output=f"Processed: {result}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
```

### Step 3: Register the provider

**Automatic registration (recommended):**

Place your provider in `core/providers/adapters/` — the pipeline's
`bootstrap_providers()` discovers and registers it automatically.

**Manual registration:**

Add to `core/providers/registry.py`:

```python
from core.providers.adapters.my_provider import MyProvider

def build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(MyProvider(), priority=10)
    ...
    return registry
```

### Step 4: Test the provider

`tests/providers/test_my_provider.py`:

```python
import pytest
from core.providers.adapters.my_provider import MyProvider

@pytest.mark.asyncio
async def test_my_provider_execute():
    provider = MyProvider()
    result = await provider.execute({"action": "do_something", "input": "hello"})
    assert result.success
    assert "hello" in result.output

@pytest.mark.asyncio
async def test_my_provider_health():
    provider = MyProvider()
    health = await provider.health()
    assert health.status.value in ("healthy", "degraded", "down")

def test_my_provider_capabilities():
    provider = MyProvider()
    caps = provider.capabilities()
    assert "my_capability" in caps.capability_names
```

Run with:

```bash
pytest tests/providers/test_my_provider.py -v
```

---

## 3. Transport Options

| Transport | When to Use | Entrypoint |
|-----------|-------------|------------|
| `python` | Default. Provider runs in-process as a Python class | `.py` file with an `ExecutionProvider` subclass |
| `mcp` | Provider exposes tools via the Model Context Protocol | `.py` file with an MCP server |
| `http` | Provider is a remote HTTP/HTTPS service | URL in `endpoint` field |
| `grpc` | Provider is a gRPC service | URL in `endpoint` field |
| `cli` | Provider is a CLI executable | Path to executable |

---

## 4. ExecutionProvider ABC

All adapters must implement three abstract methods:

### `capabilities() -> ProviderCapabilities`

Declares what this provider can do.

| Field | Purpose |
|-------|---------|
| `capability_names` | Matches against planner capability requests |
| `languages` | Programming languages supported (coding providers) |
| `frameworks` | Frameworks supported (coding providers) |
| `features` | Sub-capabilities for fine-grained routing |

### `health() -> ProviderHealth`

Returns the current health status. Called by the router to decide whether
to route work to this provider.

### `execute(task, context) -> ExecutionResult`

Performs the actual work. The `task` dict contains the capability name
and action-specific parameters. The `context` dict carries workflow
context (execution ID, artifacts, session data).

| ExecutionResult field | Purpose |
|-----------------------|---------|
| `success` | Whether execution completed without error |
| `output` | Text output |
| `error` | Error message if failed |
| `duration_ms` | Execution time |
| `exit_code` | Process exit code (if applicable) |
| `artifacts` | Mapping of artifact names to IDs |
| `metadata` | Arbitrary key-value data for calibration/learning |

---

## 5. Optional Methods

```python
async def handle_tool(self, tool_type: str, content: str, **kwargs) -> ExecutionResult | None:
    """Intercept individual tool execution. Return None to fall through to default dispatch."""

async def stream(self, task: dict, context: dict | None = None) -> AsyncIterator[str]:
    """Stream output token-by-token for real-time UI updates."""

async def cancel(self, execution_id: str) -> bool:
    """Cancel a running execution."""

async def estimate_cost(self, task: dict) -> float:
    """Estimate cost before execution (for budget-aware routing)."""

async def estimate_latency(self, task: dict) -> float:
    """Estimate latency before execution (for SLA-aware routing)."""
```

---

## 6. Complete Example: Echo Provider

A working provider that echoes input back — demonstrates every required piece.

**Manifest:** `providers/echo/provider.yaml`

```yaml
id: "echo"
publisher: "example"
version: "1.0.0"
name: "Echo Provider"
description: "Echoes input back — useful for testing"
sdk_version: 2
api_version: 1
minimum_jarvis: "3.0.0"
transport: "python"
entrypoint: "adapters/echo.py"
permissions: []
platforms: ["windows", "linux", "darwin"]
capabilities:
  - id: "echo"
    version: 1
```

**Adapter:** `providers/echo/adapters/echo.py`

```python
from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class EchoProvider(ExecutionProvider):
    provider_id = "echo"
    name = "Echo Provider"
    version = "1.0.0"
    priority = 100
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["echo"],
            features=["echo"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            status=ProviderHealthStatus.HEALTHY,
            latency_ms=0.0,
            last_checked=time.time(),
        )

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        start = time.monotonic()
        return ExecutionResult(
            success=True,
            output=task.get("input", task.get("message", "")),
            duration_ms=(time.monotonic() - start) * 1000,
        )
```

Register in `core/providers/registry.py`:

```python
from core.providers.adapters.echo import EchoProvider

def build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(EchoProvider(), priority=100)
    ...
```

Test:

```bash
pytest tests/providers/test_echo_provider.py -v
```

---

## 7. Best Practices

1. **Fail fast** — validate configuration in `__init__`, not during `execute()`.
2. **Report accurate health** — return `DOWN` when dependencies are unreachable.
3. **Set meaningful priority** — lower priority number = higher routing preference.
4. **Declare all capabilities** — the router cannot route to undeclared capabilities.
5. **Handle cancellation** — implement `cancel()` if your provider runs long operations.
6. **Include metadata** — add `metadata` to `ExecutionResult` for calibration and learning.
7. **Test health transitions** — verify healthy→degraded→down transitions.
8. **Log responsibly** — log at `DEBUG` during execution, `WARNING` on failure.

import pytest
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    RiskTier,
    ToolDefinition,
    VerificationSpec,
)
from tools.registry import ToolRegistry, new_registry, new_capability_registry


def test_registry_initially_empty():
    reg = new_registry()
    assert len(reg) == 0
    assert reg.list() == []
    assert reg.list_capabilities() == []


def test_register_tool_definition_creates_capability_companion():
    reg = new_registry()
    tool = ToolDefinition(
        name="terminal.run_command",
        description="Run a shell command",
        input_schema={"command": {"type": "string"}},
        risk_tags=["execute", "shell"],
        permission="system.shell",
    )
    reg.register(tool, owner_module="System AI")
    
    assert reg.has("terminal.run_command")
    assert reg.has_capability("terminal.run_command")
    
    cap = reg.get_capability("terminal.run_command")
    assert cap is not None
    assert cap.name == "terminal.run_command"
    assert cap.owner_module == "System AI"
    assert cap.risk == RiskTier.HIGH  # contains "execute"
    assert cap.health == CapabilityHealth.HEALTHY
    assert cap.reliability.score == 1.0


def test_register_capability_creates_tool_companion():
    reg = new_capability_registry()
    cap = CapabilityDefinition(
        name="desktop.open_project",
        type=CapabilityType.SPECIALIST_ACTION,
        owner_module="Desktop AI",
        description="Open project folder in IDE or Explorer",
        inputs={"path": {"type": "string"}},
        requirements=["filesystem", "display"],
        risk=RiskTier.LOW,
        verification=VerificationSpec(method="window_title_match", criteria={"timeout": 5.0}),
    )
    reg.register_capability(cap)
    
    assert reg.has("desktop.open_project")
    assert reg.has_capability("desktop.open_project")
    
    tool = reg.get("desktop.open_project")
    assert tool is not None
    assert tool.name == "desktop.open_project"
    assert tool.read_only is True
    assert tool.metadata["capability_type"] == "specialist"
    assert "filesystem" in tool.metadata["requirements"]


def test_reliability_metrics_and_degradation():
    reg = new_registry()
    cap = CapabilityDefinition(
        name="deployment.vercel",
        type=CapabilityType.CLI,
        owner_module="Deployment AI",
        description="Deploy app to Vercel",
        health=CapabilityHealth.HEALTHY,
    )
    reg.register_capability(cap)
    
    # 2 successes
    reg.record_execution("deployment.vercel", success=True)
    reg.record_execution("deployment.vercel", success=True)
    
    metrics = reg.get_capability("deployment.vercel").reliability
    assert metrics.total_invocations == 2
    assert metrics.successful_invocations == 2
    assert metrics.consecutive_failures == 0
    assert metrics.score == 1.0
    assert reg.get_capability("deployment.vercel").health == CapabilityHealth.HEALTHY
    
    # 3 failures -> degraded
    reg.record_execution("deployment.vercel", success=False, failure_reason="Auth token expired")
    reg.record_execution("deployment.vercel", success=False, failure_reason="Auth token expired")
    reg.record_execution("deployment.vercel", success=False, failure_reason="Auth token expired")
    
    cap = reg.get_capability("deployment.vercel")
    assert cap.reliability.consecutive_failures == 3
    assert cap.reliability.score == 0.4  # 2 / 5
    assert cap.health == CapabilityHealth.DEGRADED
    
    # 2 more failures (total 5 consecutive) -> unhealthy
    reg.record_execution("deployment.vercel", success=False, failure_reason="Auth token expired")
    reg.record_execution("deployment.vercel", success=False, failure_reason="Auth token expired")
    assert cap.health == CapabilityHealth.UNHEALTHY
    
    # recovery on success
    reg.record_execution("deployment.vercel", success=True)
    assert cap.health == CapabilityHealth.HEALTHY
    assert cap.reliability.consecutive_failures == 0


def test_run_health_checks():
    reg = new_registry()
    
    healthy_cap = CapabilityDefinition(
        name="coding.git",
        type=CapabilityType.CLI,
        owner_module="Coding AI",
        health_check=lambda: True,
    )
    failing_cap = CapabilityDefinition(
        name="unreal.cook",
        type=CapabilityType.CLI,
        owner_module="GameDev AI",
        health_check=lambda: False,
    )
    reg.register_capability(healthy_cap)
    reg.register_capability(failing_cap)
    
    results = reg.run_health_checks()
    assert results["coding.git"] == CapabilityHealth.HEALTHY
    assert results["unreal.cook"] == CapabilityHealth.UNHEALTHY
    assert reg.get_capability("unreal.cook").health == CapabilityHealth.UNHEALTHY


def test_list_capabilities_filtering():
    reg = new_registry()
    c1 = CapabilityDefinition(name="a", type=CapabilityType.TOOL, owner_module="Coding AI", risk=RiskTier.LOW)
    c2 = CapabilityDefinition(name="b", type=CapabilityType.CLI, owner_module="Desktop AI", risk=RiskTier.HIGH)
    c3 = CapabilityDefinition(name="c", type=CapabilityType.SERVICE, owner_module="Desktop AI", risk=RiskTier.LOW)
    reg.register_capability(c1)
    reg.register_capability(c2)
    reg.register_capability(c3)
    
    assert len(reg.list_capabilities(owner_module="Desktop AI")) == 2
    assert len(reg.list_capabilities(risk=RiskTier.LOW)) == 2
    assert len(reg.list_capabilities(cap_type=CapabilityType.CLI)) == 1


@pytest.mark.asyncio
async def test_execute_records_reliability():
    reg = new_registry()
    
    def add(a: int, b: int) -> int:
        return a + b
    
    tool = ToolDefinition(name="math.add", description="Add two numbers", handler=add)
    reg.register(tool)
    
    result = await reg.execute("math.add", {"a": 2, "b": 3})
    assert result.is_ok()
    assert result.output == "5"
    
    cap = reg.get_capability("math.add")
    assert cap.reliability.successful_invocations == 1
    assert cap.reliability.total_invocations == 1
    
    # Error execution
    bad_result = await reg.execute("math.add", {"invalid_param": 10})
    assert not bad_result.is_ok()
    assert cap.reliability.total_invocations == 2
    assert cap.reliability.consecutive_failures == 1

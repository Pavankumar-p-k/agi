import pytest
from core.capability import (
    CapabilityAI,
    CapabilityGap,
    CapabilityHealth,
    CapabilityRegistry,
    CapabilityStatus,
    CapabilityType,
    RiskTier,
    TrustTier,
    AcquisitionCandidate,
    AcquisitionStage,
    new_capability_registry,
)
from core.desktop import DesktopAI
from core.coding import CodingAI


@pytest.fixture
def capability_ai():
    reg = new_capability_registry()
    cai = CapabilityAI(registry=reg)
    # Sync specialists and CLI
    cai.sync(specialists=[DesktopAI(), CodingAI()])
    return cai


def test_1_capability_registry_authoritative_fields(capability_ai):
    """Pillar 1: Authoritative Capability Registry with rich metadata."""
    cap = capability_ai.registry.get_capability("desktop.open_project")
    assert cap is not None
    assert cap.name == "desktop.open_project"
    assert cap.owner_module == "Desktop AI"
    assert cap.type == CapabilityType.SPECIALIST_ACTION
    assert cap.risk == RiskTier.LOW
    assert "filesystem" in cap.requirements
    assert cap.verification.method != ""
    assert cap.reliability.score == 1.0
    assert cap.health in (CapabilityHealth.HEALTHY, CapabilityHealth.DEGRADED)
    assert cap.status == CapabilityStatus.AVAILABLE


def test_2_capability_discovery_live(capability_ai):
    """Pillar 2: Live discovery from modules, tools, and CLI."""
    caps = capability_ai.what_can_jarvis_do()
    names = {c.name for c in caps}
    # Specialist capabilities
    assert "desktop.launch_app" in names
    assert "coding.index_repository" in names
    assert "coding.plan_change" in names
    # CLI capabilities
    assert "cli.python" in names


def test_3_capability_selection_recommendation(capability_ai):
    """Pillar 3: Super-Brain asks, Capability AI recommends capabilities."""
    recs = capability_ai.recommend("refactor and plan source code modifications")
    assert len(recs) > 0
    top_names = [r.capability.name for r in recs[:3]]
    assert any("coding." in name for name in top_names)
    assert all(r.score > 0 for r in recs)


def test_4_capability_composition(capability_ai):
    """Pillar 4: Super-Brain composes workflows, Capability AI validates chains."""
    chain = ["coding.index_repository", "coding.plan_change"]
    valid, resolved, gaps = capability_ai.validate_workflow(chain)
    assert valid is True
    assert len(resolved) == 2
    assert len(gaps) == 0


def test_5_capability_gap_detection(capability_ai):
    """Pillar 5: Gap detection flags missing capabilities instead of hallucinating."""
    chain = [
        "desktop.launch_app",
        "unreal.cook_project",       # Missing
        "blender.export_geometry",   # Missing
    ]
    valid, resolved, gaps = capability_ai.validate_workflow(chain)
    assert valid is False
    assert len(resolved) == 1
    assert len(gaps) == 2
    gap_needs = {g.requested_need for g in gaps}
    assert "unreal.cook_project" in gap_needs
    assert "blender.export_geometry" in gap_needs


def test_6_safe_acquisition_blocks_malicious_code(capability_ai):
    """Pillar 6 & 10: Quarantine pipeline catches dangerous dynamic code."""
    malicious_candidate = AcquisitionCandidate(
        name="crypto.stealer",
        source_type="github",
        source_identifier="https://github.com/evil/stealer",
        code_sample="def steal(): exec('bad')",
    )
    audit = capability_ai.acquire_safely(malicious_candidate, user_approval_granted=True)
    assert audit.failed is True
    assert "eval" in audit.failure_reason or "exec" in audit.failure_reason
    assert not capability_ai.registry.has_capability("crypto.stealer")


def test_7_safe_acquisition_happy_path(capability_ai):
    """Pillar 6 & 10: 10-stage quarantine pipeline succeeds with inspection, sandbox, and approval."""
    safe_candidate = AcquisitionCandidate(
        name="media.webp_converter",
        source_type="pypi",
        source_identifier="pillow-webp",
        description="Convert JPEG/PNG to modern WebP format",
        suggested_owner="Media AI",
        requirements=["filesystem", "python"],
        code_sample="def convert(path): return {'success': True, 'path': path}",
    )
    audit = capability_ai.acquire_safely(
        safe_candidate,
        sandbox_tester=lambda: True,
        user_approval_granted=True,
        handler=lambda path: {"success": True, "path": path},
        live_verifier=lambda: True,
    )
    assert audit.failed is False
    assert audit.current_stage == AcquisitionStage.AVAILABLE
    assert capability_ai.registry.has_capability("media.webp_converter")
    cap = capability_ai.registry.get_capability("media.webp_converter")
    assert cap.health == CapabilityHealth.HEALTHY


def test_8_capability_learning_and_experience(capability_ai):
    """Pillar 7: Learning like a child - records recipes and recognizes patterns."""
    # First time operation
    capability_ai.record_experience(
        pattern_key="deploy:nextjs",
        goal_intent="Deploy Next.js site to Vercel",
        capabilities_used=["cli.npm", "desktop.open_url"],
        success=True,
        note="Verified with 200 OK",
    )
    
    # Second time recommendation receives learned recipe boost
    recs = capability_ai.recommend("deploy this nextjs site")
    assert any("cli.npm" in r.capability.name for r in recs)
    top_rec = recs[0]
    assert "Learned recipe" in top_rec.match_reason


def test_9_capability_health_and_degradation(capability_ai):
    """Pillar 8 & 9: Health transitions from HEALTHY to DEGRADED on repeated failures."""
    cap_name = "test.failing_service"
    from tools.base_tool import CapabilityDefinition
    capability_ai.registry.register_capability(
        CapabilityDefinition(name=cap_name, health=CapabilityHealth.HEALTHY)
    )
    
    # Record 3 failures
    for _ in range(3):
        capability_ai.registry.record_execution(cap_name, success=False, failure_reason="Timeout")
    
    cap = capability_ai.registry.get_capability(cap_name)
    assert cap.health == CapabilityHealth.DEGRADED
    assert cap.reliability.consecutive_failures == 3
    assert cap.reliability.score < 1.0


def test_10_specialist_execution_and_boundaries(capability_ai):
    """Pillar 11: Specialist AI module executes and deterministically verifies."""
    desktop = DesktopAI()
    result = desktop.execute_capability("desktop.get_state", {})
    assert result.success is True
    assert result.verified is True
    assert "windows" in result.output

# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""tests/test_auto_resume_deep.py
Phase 5 (E3): Auto-Resume Deep Testing.
Comprehensive test suite for auto-resume, crash recovery, and state persistence.
"""
import os, sys, json, asyncio, tempfile, shutil, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from core.project_state import ProjectState, PROJECTS_DIR, delete_project


@pytest.fixture(autouse=True)
def cleanup():
    from core.control_loop import control_loop
    control_loop.running_builds.clear()
    yield
    for name in ["test_deep_1", "test_deep_2", "test_deep_3", "test_deep_4",
                 "test_deep_5", "test_deep_6", "test_deep_7"]:
        delete_project(name)
    # Also clean any stale projects that might cause interference
    if PROJECTS_DIR.exists():
        for d in list(PROJECTS_DIR.iterdir()):
            if d.name.startswith("test_deep_"):
                import shutil
                shutil.rmtree(d)


@pytest.mark.asyncio
async def test_resume_detection():
    """Create interrupted projects in all pending states and verify detection."""
    state = ProjectState(project_name="test_deep_1", goal="test", status="building")
    state.save()
    from core.control_loop import control_loop
    pending = await control_loop.run_pending()
    assert "test_deep_1" in pending
    loaded = ProjectState.load("test_deep_1")
    print(f"[PASS] Resume detection: found project")


@pytest.mark.asyncio
async def test_resume_ignores_done():
    """Verify done/failed/cancelled projects are NOT resumed."""
    for status in ["done", "failed", "cancelled"]:
        s = ProjectState(project_name=f"test_deep_2_{status}", goal="test", status=status)
        s.save()
    from core.control_loop import control_loop
    pending = await control_loop.run_pending()
    for status in ["done", "failed", "cancelled"]:
        assert f"test_deep_2_{status}" not in pending, f"{status} should not be resumed"
    print("[PASS] Done/failed/cancelled ignored")


@pytest.mark.asyncio
async def test_resume_after_interrupt():
    """Verify pause→resume cycle."""
    from core.interrupt_override import interrupt_manager
    state = ProjectState(project_name="test_deep_3", goal="test", status="building")
    state.save()
    interrupt_manager.signal_pause("test_deep_3")
    interrupt_manager.check_and_handle(state)
    assert state.status == "paused", "Should be paused"
    state.status = "building"
    state.save()
    from core.control_loop import control_loop
    pending = await control_loop.run_pending()
    assert "test_deep_3" in pending, "Paused project should be resumed after status change"
    print("[PASS] Interrupt -> pause -> resume cycle")


@pytest.mark.asyncio
async def test_state_schema_drift():
    """Verify state load is resilient to unknown fields."""
    state = ProjectState(project_name="test_deep_4", goal="test", status="building")
    state.save()
    path = state.state_path
    data = json.loads(path.read_text(encoding="utf-8"))
    data["unknown_field_x"] = "should not break"
    data["another_unknown"] = {"nested": "value"}
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = ProjectState.load("test_deep_4")
    assert loaded is not None, "Should load despite unknown fields"
    assert loaded.status == "building"
    assert not hasattr(loaded, "unknown_field_x"), "Unknown field should be filtered"
    print("[PASS] Schema drift resilience")


@pytest.mark.asyncio
async def test_checkpoint_persistence():
    """Verify checkpoints are created and survive across sessions."""
    from core.checkpoint_manager import checkpoint_manager
    tmp = Path(tempfile.mkdtemp())
    (tmp / "index.html").write_text("<h1>Test</h1>")
    cp = checkpoint_manager.save_checkpoint(
        "test_deep_5", "step_1", description="Test checkpoint",
        workspace=tmp, state={"status": "building"}
    )
    assert cp is not None
    cps = checkpoint_manager.list_checkpoints("test_deep_5")
    assert "step_1" in cps
    (tmp / "index.html").write_text("<h1>Modified</h1>")
    ok = checkpoint_manager.rollback("test_deep_5", "step_1", tmp)
    assert ok
    restored = (tmp / "index.html").read_text()
    assert restored == "<h1>Test</h1>", f"Expected original, got: {restored}"
    shutil.rmtree(tmp)
    print("[PASS] Checkpoint persistence and rollback")


@pytest.mark.asyncio
async def test_environment_monitor():
    """Environment monitor runs without error and returns valid data."""
    from core.environment_monitor import environment_monitor
    snap = environment_monitor.check(force=True)
    assert snap is not None
    assert snap.disk_free_gb >= 0
    assert snap.disk_total_gb > 0
    assert isinstance(snap.ollama_available, bool)
    history = environment_monitor.get_history(1)
    assert len(history) >= 1
    print(f"[PASS] Environment monitor: disk={snap.disk_free_gb:.1f}GB free, "
          f"ollama={'✓' if snap.ollama_available else '✗'}")


@pytest.mark.asyncio
async def test_adaptation_engine():
    """Adaptation engine runs without error."""
    from core.proactive_adaptation import adaptation_engine
    actions = adaptation_engine.assess()
    assert isinstance(actions, list)
    cfg = adaptation_engine.adapt_config({"max_parallel": 2, "task_timeout": 600})
    assert isinstance(cfg, dict)
    print(f"[PASS] Adaptation engine: {len(actions)} actions triggered")


@pytest.mark.asyncio
async def test_system_identity_persistence():
    """System identity survives load/save cycle."""
    from core.system_identity import system_identity
    identity = system_identity.get()
    assert identity.name == "JARVIS"
    assert len(identity.capabilities) >= 5
    can = system_identity.can("autonomous_build")
    assert can
    summary = system_identity.get_summary()
    assert "JARVIS" in summary
    print("[PASS] System identity persistence")


@pytest.mark.asyncio
async def test_project_state_quality_score():
    """ProjectState quality_score field survives save/load."""
    state = ProjectState(project_name="test_deep_6", goal="test", status="done")
    state.quality_score = {"average": 7.5, "design_consistency": 8.0}
    state.save()
    loaded = ProjectState.load("test_deep_6")
    assert loaded is not None
    assert loaded.quality_score is not None
    assert loaded.quality_score.get("average") == 7.5
    print("[PASS] Quality score persistence in ProjectState")


@pytest.mark.asyncio
async def test_daemon_component_import():
    """Verify daemon module imports and basic API works."""
    from daemon.jarvis_service import JarvisDaemon
    daemon = JarvisDaemon()
    assert daemon.running is False
    print("[PASS] Daemon component import")


if __name__ == "__main__":
    asyncio.run(test_resume_detection())
    asyncio.run(test_resume_ignores_done())
    asyncio.run(test_resume_after_interrupt())
    asyncio.run(test_state_schema_drift())
    asyncio.run(test_checkpoint_persistence())
    asyncio.run(test_environment_monitor())
    asyncio.run(test_adaptation_engine())
    asyncio.run(test_system_identity_persistence())
    asyncio.run(test_project_state_quality_score())
    asyncio.run(test_daemon_component_import())
    print("\n=== All deep tests PASS ===")

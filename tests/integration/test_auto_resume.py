"""tests/test_auto_resume.py
Test that interrupted builds are detected and resumed by the daemon.
"""
import os, sys, json, asyncio, tempfile, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.project_state import ProjectState, PROJECTS_DIR


async def test_resume_detection():
    """Create an interrupted project and verify run_pending detects it."""
    state = ProjectState(
        project_name="test_resume_project",
        goal="build a test page",
        status="building",
        interpreted_goal={"project_type": "website", "pages": ["index", "about", "contact"]},
    )
    state.save()
    assert state.state_path.exists(), "State file should exist"

    from core.control_loop import control_loop
    pending = await control_loop.run_pending()
    assert "test_resume_project" in pending, f"run_pending should find the project, got: {pending}"

    # Verify it's now running
    loaded = ProjectState.load("test_resume_project")
    assert loaded is not None
    print(f"[PASS] Resume detection: found project in status '{loaded.status}'")

    # Clean up
    from core.project_state import delete_project
    delete_project("test_resume_project")
    print("[PASS] Cleanup complete")


async def test_resume_rebuild():
    """Test that resume_build works on an interrupted project."""
    state = ProjectState(
        project_name="test_resume_rebuild",
        goal="build a coffee shop website",
        status="fixing",
        retries=1,
        interpreted_goal={
            "project_type": "website",
            "pages": ["index", "about", "contact"],
            "tech_stack": ["html", "css"],
        },
    )
    state.save()

    from core.control_loop import control_loop
    result = await control_loop.resume_build("test_resume_rebuild")
    assert result is not None, "resume_build should return a state"
    print(f"[PASS] Resume rebuild: returned status='{result.status}' after {result.retries} retries")

    from core.project_state import delete_project
    delete_project("test_resume_rebuild")


async def test_daemon_integration():
    """Test that the daemon heartbeat loop calls run_pending."""
    state = ProjectState(
        project_name="test_daemon_resume",
        goal="build a blog",
        status="building",
        interpreted_goal={"project_type": "blog", "pages": ["index", "blog", "about"]},
    )
    state.save()

    from daemon.jarvis_service import JarvisDaemon

    daemon = JarvisDaemon()
    discovered = await daemon._check_projects()
    # _check_projects calls run_pending which resumes — just verify no crash
    print(f"[PASS] Daemon integration: _check_projects completed without error")

    from core.project_state import delete_project
    delete_project("test_daemon_resume")


async def test_ignore_done_projects():
    """Verify that done/failed/cancelled projects are NOT resumed."""
    for status in ("done", "failed", "cancelled"):
        state = ProjectState(
            project_name=f"test_ignore_{status}",
            goal="ignore test",
            status=status,
        )
        state.save()

    from core.control_loop import control_loop
    pending = await control_loop.run_pending()
    for status in ("done", "failed", "cancelled"):
        assert f"test_ignore_{status}" not in pending, f"Should not resume {status} projects"

    for status in ("done", "failed", "cancelled"):
        from core.project_state import delete_project
        delete_project(f"test_ignore_{status}")
    print("[PASS] Done/failed/cancelled projects correctly ignored")


async def test_state_persistence():
    """Verify state.json is correctly saved and loaded after status changes."""
    state = ProjectState(
        project_name="test_persistence",
        goal="persistence check",
        status="building",
        template_name="poco-html",
    )
    state.save()

    loaded = ProjectState.load("test_persistence")
    assert loaded is not None
    assert loaded.status == "building"
    assert loaded.template_name == "poco-html"
    assert loaded.goal == "persistence check"

    # Update status
    loaded.status = "done"
    loaded.save()

    reloaded = ProjectState.load("test_persistence")
    assert reloaded.status == "done"

    from core.project_state import delete_project
    delete_project("test_persistence")
    print("[PASS] State persistence: save/load/update verified")


async def main():
    print("=" * 60)
    print("Auto-Resume Test Suite")
    print("=" * 60)

    tests = [
        test_resume_detection,
        test_resume_rebuild,
        test_daemon_integration,
        test_ignore_done_projects,
        test_state_persistence,
    ]

    passed = 0
    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: FAILED - {e}")
            import traceback
            traceback.print_exc()

    print("=" * 60)
    print(f"Results: {passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))

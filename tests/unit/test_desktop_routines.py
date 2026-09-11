from core.desktop.routines import DesktopRoutineManager


def test_routine_requires_repeated_verified_observations(tmp_path):
    manager = DesktopRoutineManager(tmp_path / "routines.json")
    action = {"tool": "launch_app", "args": {"app": "Notepad"}}
    assert manager.observe("Open Notepad", [action], verified=False) is None
    assert manager.observe("Open Notepad", [action]) is None
    assert manager.observe("Open Notepad", [action]) is None
    proposal = manager.observe("Open Notepad", [action])
    assert proposal is not None
    assert proposal.confidence >= 0.5
    assert proposal.status == "pending"


def test_routine_cannot_execute_before_approval(tmp_path):
    manager = DesktopRoutineManager(tmp_path / "routines.json")
    action = {"tool": "focus_window", "args": {"title": "Notepad"}}
    for _ in range(3):
        proposal = manager.observe("Focus Notepad", [action])
    calls = []
    try:
        manager.execute_approved(proposal.proposal_id, calls.append)
    except PermissionError:
        pass
    else:
        raise AssertionError("unapproved routine executed")
    manager.approve(proposal.proposal_id)
    manager.execute_approved(proposal.proposal_id, calls.append)
    assert calls == [action]


def test_routine_can_be_revoked_and_audited(tmp_path):
    manager = DesktopRoutineManager(tmp_path / "routines.json")
    action = {"tool": "launch_app", "args": {"app": "Notepad"}}
    for _ in range(3):
        proposal = manager.observe("Launch Notepad", [action])
    manager.approve(proposal.proposal_id)
    manager.revoke(proposal.proposal_id)
    assert proposal.status == "revoked"
    assert [entry["event"] for entry in manager.audit_log][-2:] == ["approved", "revoked"]

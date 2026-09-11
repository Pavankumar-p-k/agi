import asyncio

from core.desktop.specialist import (
    DesktopActionRecord,
    DesktopExecutionRequest,
    DesktopExecutionResult,
    DesktopExecutionStatus,
    DesktopRecoveryAttempt,
    DesktopSpecialist,
    DesktopVerification,
)
from core.desktop.specialist_state import DesktopLocalState


def test_specialist_executes_async_handler_and_returns_structured_result():
    async def handler(request):
        return {
            "status": "completed",
            "result": {"goal": request.goal},
            "observations": [{"active_window": "Notepad"}],
            "actions_taken": [
                {
                    "action": "focus",
                    "target": "Notepad",
                    "success": True,
                    "verified": True,
                }
            ],
            "verification": {"verified": True, "reason": "window focused"},
        }

    request = DesktopExecutionRequest("focus Notepad")
    result = asyncio.run(DesktopSpecialist(handler).execute(request))

    assert result.status is DesktopExecutionStatus.COMPLETED
    assert result.request_id == request.request_id
    assert result.verification.verified is True
    assert result.actions_taken[0].target == "Notepad"
    assert result.completed_at is not None


def test_request_rejects_empty_goal():
    try:
        DesktopExecutionRequest(" ")
    except ValueError as error:
        assert str(error) == "goal is required"
    else:
        raise AssertionError("empty goal must be rejected")


def test_local_state_records_desktop_execution_only():
    state = DesktopLocalState()
    request = DesktopExecutionRequest("inspect desktop")
    state.begin_task(request.request_id, request.goal)
    state.record_result(
        DesktopExecutionResult(
            status=DesktopExecutionStatus.PARTIAL,
            observations=[{"windows": 2}],
            actions_taken=[
                DesktopActionRecord(action="list_windows", success=True, verified=True)
            ],
            verification=DesktopVerification(True),
            remaining_work=["identify target window"],
            request_id=request.request_id,
        )
    )

    assert state.current_task is None
    assert state.observations == [{"windows": 2}]
    assert state.execution_history[0]["status"] == "partial"
    assert state.execution_history[0]["remaining_work"] == ["identify target window"]


def test_unverified_completed_result_becomes_verification_failure():
    result = asyncio.run(
        DesktopSpecialist(
            lambda request: {
                "status": "completed",
                "result": {"window": "missing"},
                "verification": {"verified": False, "reason": "window not found"},
            }
        ).execute(DesktopExecutionRequest("focus missing window"))
    )

    assert result.status is DesktopExecutionStatus.VERIFICATION_FAILED
    assert result.verification.verified is False
    assert "window not found" in result.errors
    assert result.remaining_work == ["focus missing window"]


def test_handler_failures_are_structured_and_recovery_is_preserved():
    def broken_handler(request):
        raise PermissionError("access denied")

    result = asyncio.run(
        DesktopSpecialist(broken_handler).execute(
            DesktopExecutionRequest("read protected file")
        )
    )

    assert result.status is DesktopExecutionStatus.BLOCKED
    assert result.errors == ["PermissionError: access denied"]
    assert result.remaining_work == ["read protected file"]

    recovery = DesktopSpecialist._coerce_result(
        {
            "status": "partial",
            "recovery_attempts": [
                {
                    "action": "refocus_window",
                    "success": True,
                    "verified": True,
                    "evidence": {"title": "Notepad"},
                }
            ],
        },
        "request-1",
    )
    assert recovery.recovery_attempts[0] == DesktopRecoveryAttempt(
        action="refocus_window",
        success=True,
        verified=True,
        evidence={"title": "Notepad"},
    )


def test_unexpected_handler_exception_is_not_reported_as_success():
    result = asyncio.run(
        DesktopSpecialist(
            lambda request: (_ for _ in ()).throw(RuntimeError("UIA drift"))
        ).execute(DesktopExecutionRequest("click Submit"))
    )

    assert result.status is DesktopExecutionStatus.FAILED
    assert result.errors == ["RuntimeError: UIA drift"]
    assert result.remaining_work == ["click Submit"]


def test_timeout_is_partial_and_cancellation_is_truthful():
    async def timed_out(request):
        raise TimeoutError("UIA operation timed out")

    timed_out_result = asyncio.run(
        DesktopSpecialist(timed_out).execute(
            DesktopExecutionRequest("invoke Save")
        )
    )
    assert timed_out_result.status is DesktopExecutionStatus.PARTIAL
    assert timed_out_result.remaining_work == ["invoke Save"]

    async def cancelled(request):
        raise asyncio.CancelledError()

    cancelled_result = asyncio.run(
        DesktopSpecialist(cancelled).execute(
            DesktopExecutionRequest("close dialog")
        )
    )
    assert cancelled_result.status is DesktopExecutionStatus.PARTIAL
    assert cancelled_result.errors == ["Desktop execution was cancelled"]
    assert cancelled_result.remaining_work == ["close dialog"]

"""Crash recovery: re-spawn active workflows with stale heartbeats."""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def recover_active_workflows(engine, stale_seconds: float = 60.0) -> list[dict]:
    """Resume stale RUNNING/COMPENSATING workflows that have no live task.

    Returns one {"workflow_id", "workflow_type", "status"} dict per recovered
    workflow. Live tasks (tracked in ``engine._running``) and workflows with
    recent heartbeats are skipped.
    """
    recovered: list[dict] = []
    store = engine.store
    for wf in store.get_active_workflows():
        wid = wf.workflow_id
        task = engine._running.get(wid)
        if task is not None and not task.done():
            continue
        if wf.last_heartbeat is None:
            stale = True
        else:
            age = (datetime.utcnow() - wf.last_heartbeat).total_seconds()
            stale = age > stale_seconds
        if not stale:
            continue
        try:
            await engine.resume_workflow(wid)
        except Exception as exc:  # noqa: BLE001 — one bad workflow must not stop recovery
            logger.warning("recovery failed for %s: %s", wid, exc)
            continue
        status = wf.status.value if hasattr(wf.status, "value") else str(wf.status)
        recovered.append({
            "workflow_id": wid,
            "workflow_type": wf.workflow_type,
            "status": status,
        })
        logger.info("recovered stale workflow %s (%s)", wid, wf.workflow_type)
    return recovered

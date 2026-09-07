from __future__ import annotations

from .contracts import HealthStatus, WorkerResponse


class LocalWorker:
    async def execute(self, request):
        return WorkerResponse(outcome=request.request if hasattr(request, "request") else request)

    async def health(self):
        return HealthStatus.HEALTHY

    async def heartbeat(self):
        return None

    async def shutdown(self):
        return None

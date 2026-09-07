from __future__ import annotations

import inspect


class InProcessTransport:
    def __init__(self, worker_fn):
        self.worker_fn = worker_fn

    async def send(self, request):
        result = self.worker_fn(request)
        return await result if inspect.isawaitable(result) else result

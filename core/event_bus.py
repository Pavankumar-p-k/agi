import asyncio
import inspect
import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_subscribers: dict[str, list] = defaultdict(list)


def subscribe(event: str, callback) -> None:
    with _lock:
        _subscribers[event].append(callback)


def unsubscribe(event: str, callback) -> None:
    with _lock:
        try:
            _subscribers[event].remove(callback)
        except ValueError:
            pass


def fire_event(event: str, data=None) -> None:
    with _lock:
        handlers = list(_subscribers.get(event, []))
        wildcard = list(_subscribers.get("*", []))
    all_handlers = handlers + wildcard
    if not all_handlers:
        logger.debug("Event: %s data=%s (no subscribers)", event, data)
        return
    for handler in all_handlers:
        try:
            if inspect.iscoroutinefunction(handler):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(handler(event, data))
                    else:
                        loop.run_until_complete(handler(event, data))
                except RuntimeError:
                    asyncio.run(handler(event, data))
            else:
                handler(event, data)
        except Exception as _e:
            logger.debug("event_bus handler failed: %s", _e)
            logger.exception("Event handler failed for %s", event)


def get_task_scheduler():
    try:
        from core.scheduler import scheduler
        return scheduler
    except ImportError:
        logger.warning("scheduler not available")
        return None

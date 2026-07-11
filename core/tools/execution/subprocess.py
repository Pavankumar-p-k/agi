import asyncio
import collections
import logging
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

DEFAULT_BASH_TIMEOUT = 60 * 60
DEFAULT_PYTHON_TIMEOUT = 60 * 60
PROGRESS_INTERVAL_S = 2.0
PROGRESS_TAIL_LINES = 12


async def _run_subprocess_streaming(
    proc: asyncio.subprocess.Process,
    *,
    timeout: float,
    progress_cb: Callable[[dict], Awaitable[None]] | None = None,
) -> tuple[str, str, int | None, bool]:
    started = time.time()
    stdout_full: list[str] = []
    stderr_full: list[str] = []
    tail = collections.deque(maxlen=PROGRESS_TAIL_LINES)

    async def _reader(stream, full_buf, label: str):
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip("\n")
            full_buf.append(decoded)
            if label == "err":
                tail.append(f"! {decoded}")
            else:
                tail.append(decoded)

    async def _progress_emitter():
        await asyncio.sleep(PROGRESS_INTERVAL_S)
        while True:
            if progress_cb:
                try:
                    await progress_cb({
                        "elapsed_s": round(time.time() - started, 1),
                        "tail": "\n".join(list(tail)),
                    })
                except Exception as _e:
                    logger.debug("progress callback failed: %s", _e)
            await asyncio.sleep(PROGRESS_INTERVAL_S)

    rd_out = asyncio.create_task(_reader(proc.stdout, stdout_full, "out"))
    rd_err = asyncio.create_task(_reader(proc.stderr, stderr_full, "err"))
    prog_task = asyncio.create_task(_progress_emitter()) if progress_cb else None

    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except Exception as _e:
            logger.debug("kill on timeout failed: %s", _e)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception as _e:
            logger.debug("wait after kill on timeout failed: %s", _e)
    except asyncio.CancelledError:
        try:
            proc.kill()
        except Exception as _e:
            logger.debug("kill on cancel failed: %s", _e)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception as _e:
            logger.debug("wait after kill on cancel failed: %s", _e)
        for t in (rd_out, rd_err):
            t.cancel()
        if prog_task is not None:
            prog_task.cancel()
        raise
    finally:
        if prog_task is not None and not prog_task.done():
            prog_task.cancel()
            try:
                await prog_task
            except (asyncio.CancelledError, Exception):
                pass
        for t in (rd_out, rd_err):
            try:
                await asyncio.wait_for(t, timeout=1)
            except Exception as _e:
                logger.debug("reader drain cancelled: %s", _e)

    return (
        "\n".join(stdout_full),
        "\n".join(stderr_full),
        proc.returncode,
        timed_out,
    )

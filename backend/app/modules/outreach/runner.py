"""Send today's invitations now, from the admin screen, inside the API process.

The timer (``app.scripts.outreach_send``) spaces messages 30-90 s apart over
the morning. "Send now" is the same batch with a shorter gap, started as a
background task so the request returns at once; the screen then watches
``sent_today`` grow. Each contact is committed as it goes, so a worker
restart mid-run leaves the rest queued for the next run, never re-sent, and
the batch re-checks the day's budget before every message, so a run started
in two workers at once still stops at the daily number.
"""

from __future__ import annotations

import asyncio
import random

import structlog

from app.core import deps
from app.core.outreach_mail import OutreachSender
from app.modules.outreach import service

log = structlog.get_logger("app.outreach")
SPACING_SECONDS: tuple[float, float] = (5.0, 10.0)

_task: asyncio.Task | None = None


def is_running() -> bool:
    return _task is not None and not _task.done()


async def _job(sender: OutreachSender) -> dict[str, int]:
    lo, hi = SPACING_SECONDS
    async with deps.bypass_session_scope() as session:
        return await service.send_batch(session, sender, force=True, pause=lambda: asyncio.sleep(random.uniform(lo, hi)))


def _finished(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    if (exc := task.exception()) is not None:
        log.error("outreach_send_now_failed", error=f"{type(exc).__name__}: {exc}"[:300])
    else:
        log.info("outreach_send_now_done", **task.result())


def start(sender: OutreachSender) -> bool:
    """Start the batch; False when one is already running in this process."""
    global _task
    if is_running():
        return False
    _task = asyncio.create_task(_job(sender))
    _task.add_done_callback(_finished)
    return True


async def wait() -> dict[str, int] | None:
    """Test hook: the running batch's report, once it is done."""
    return await _task if _task is not None else None

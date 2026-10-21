"""Shared flag for retention purges that also delete stored files.

``app.scripts.retention_purge --dry-run`` rolls the database back, but a
deleted object cannot be rolled back, so purges check ``DRY_RUN`` before
touching storage.
"""

from contextvars import ContextVar

DRY_RUN: ContextVar[bool] = ContextVar("retention_dry_run", default=False)

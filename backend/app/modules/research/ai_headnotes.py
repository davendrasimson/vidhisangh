"""Queue and store AI-generated headnotes for Supreme Court judgments.

Headnotes are written outside the app (by a person working with an AI model,
e.g. in a Claude Code session) from files this module exports, then imported
back. No paid API is called from here. The work runs newest judgment first and is
resumable: `export_queue` only returns judgments that have no AI headnote yet.

Every stored headnote is flagged as AI-generated (`AiHeadnoteRead.ai_generated`)
and records the model, time and format version that produced it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.judgment_enrichment import _judgment_body
from app.modules.research.models import CourtLevel, Judgment
from app.modules.research.schemas import AiHeadnoteContent

FORMAT_VERSION = "1"


@dataclass(frozen=True)
class QueueItem:
    id: uuid.UUID
    citation: str | None
    case_name: str
    judgment_date: str | None
    bench: str | None
    acts: list[str]
    text: str


def _pending():
    return (
        select(Judgment)
        .where(
            Judgment.court_level == CourtLevel.SUPREME_COURT,
            Judgment.full_text.is_not(None),
            Judgment.ai_headnote.is_(None),
        )
    )


async def export_queue(session: AsyncSession, limit: int, skip: set[uuid.UUID] | None = None) -> list[QueueItem]:
    """The next `limit` Supreme Court judgments without an AI headnote, newest first.

    The text handed out is the judgment body only: anything before the start of
    the judgment proper (where a reporter's editorial headnote would sit) is cut,
    so the writer never sees, and cannot paraphrase, copyrighted editorial text.
    """
    stmt = _pending().order_by(Judgment.judgment_date.desc().nulls_last(), Judgment.citation, Judgment.id)
    if skip:
        stmt = stmt.where(Judgment.id.not_in(skip))
    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    return [
        QueueItem(
            id=j.id,
            citation=j.citation,
            case_name=j.cause_title or j.case_name,
            judgment_date=j.judgment_date.isoformat() if j.judgment_date else None,
            bench=j.bench,
            acts=list(j.acts or []),
            text=_judgment_body(j.full_text or ""),
        )
        for j in rows
    ]


async def pending_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(_pending().subquery()))).scalar_one()


async def done_count(session: AsyncSession) -> int:
    stmt = select(func.count()).where(
        Judgment.court_level == CourtLevel.SUPREME_COURT, Judgment.ai_headnote.is_not(None)
    )
    return (await session.execute(stmt)).scalar_one()


class HeadnoteImportError(ValueError):
    pass


async def apply_ai_headnote(
    session: AsyncSession,
    judgment_id: uuid.UUID,
    content: dict,
    *,
    model: str,
    force: bool = False,
    now: datetime | None = None,
) -> Judgment:
    """Validate and store one headnote. Refuses non-SC rows and, unless `force`,
    rows that already have one, so a stale file can never overwrite newer work."""
    data = AiHeadnoteContent.model_validate(content).model_dump()
    judgment = await session.get(Judgment, judgment_id)
    if judgment is None:
        raise HeadnoteImportError(f"judgment {judgment_id} not found")
    if judgment.court_level != CourtLevel.SUPREME_COURT:
        raise HeadnoteImportError(f"judgment {judgment_id} is not a Supreme Court judgment")
    if judgment.ai_headnote and not force:
        raise HeadnoteImportError(f"judgment {judgment_id} already has an AI headnote (use force)")
    if not model.strip():
        raise HeadnoteImportError("model name is required")
    judgment.ai_headnote = data
    judgment.ai_headnote_model = model.strip()[:80]
    judgment.ai_headnote_generated_at = now or datetime.now(UTC)
    judgment.ai_headnote_version = FORMAT_VERSION
    await session.flush()
    return judgment

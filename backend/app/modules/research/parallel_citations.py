"""Mine parallel citations (SCC, AIR, …) for library judgments from judgment texts.

A Supreme Court judgment that relies on an earlier case writes it the way
practice does — "K.S. Puttaswamy v. Union of India, (2017) 10 SCC 1". The
library holds that earlier case under its SCR / INSC citation only. This module
reads every citation in a judgment's text with the cite check's own parser,
resolves the case named next to it in the Supreme Court corpus (parties + the
reporter's year window), and counts, per citation, which record the citing
judgments agree on. The winner becomes a `JudgmentAlias`, with the number of
agreeing judgments as `support`.

Only reporters that report the Supreme Court are mined (SCC, AIR … SC, SCALE,
JT, Cri LJ); SCC OnLine and AIR entries for High Courts are left alone because
the corpus cannot resolve them by name. Run by ``app.scripts.parallel_citations``.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.research.cite_check import MAX_TEXT_CHARS, FoundCitation, _year_window, find_citations, party_tokens
from app.modules.research.models import CourtLevel, Judgment, JudgmentAlias
from app.modules.research.repository import ResearchRepository

# Reporter citations that denote Supreme Court decisions and so can be resolved here.
_MINEABLE = re.compile(r"^(\(\d{4}\) \d+ SCC\b(?! OnLine)|\d{4} Supp \(\d+\) SCC\b|AIR \d{4} (SC|SCW) \d|\d{4} \(\d+\) SCALE |JT \d{4} \(\d+\) SC |\d{4} Cri LJ )")


def mineable(found: FoundCitation) -> bool:
    return found.kind == "reporter" and bool(_MINEABLE.match(found.normalised))


@dataclass
class Votes:
    reporter: str
    year: int
    kind: str
    names: Counter = field(default_factory=Counter)        # case name as cited → occurrences
    citing: set = field(default_factory=set)                # judgments citing it (support)


def collect(text: str, citing_id: uuid.UUID, votes: dict[str, Votes]) -> int:
    """Add every mineable citation in one judgment's text to the votes. Returns how many."""
    n = 0
    # The parser refuses drafts over its limit; a long judgment is simply read up to it.
    for found in find_citations(text[:MAX_TEXT_CHARS]):
        if not mineable(found):
            continue
        v = votes.setdefault(found.normalised, Votes(found.reporter, found.year, found.kind))
        v.citing.add(citing_id)
        for name in found.case_names:
            v.names[name] += 1
        n += 1
    return n


@dataclass
class Resolved:
    citation: str
    judgment_id: uuid.UUID
    reporter: str
    support: int
    case_name_as_cited: str


async def resolve(repo: ResearchRepository, citation: str, v: Votes, *, exclude: set[uuid.UUID] | None = None) -> Resolved | None:
    """The one Supreme Court record the names cited next to this citation point to, or None.

    Each distinct cited name is looked up by its party tokens in the reporter's
    year window; a record wins when it is the only one those names agree on and
    the citation is not the citing judgment's own.
    """
    if not v.names:
        return None
    lo, hi = _year_window(v.year, v.kind)
    hits: Counter = Counter()
    for name, weight in v.names.most_common(4):
        tokens = party_tokens(name)
        if not tokens:
            continue
        # Best effort: a lookup the database cancels (statement timeout on a
        # pathological token set) costs this name its vote, not the whole run.
        try:
            async with repo.session.begin_nested():
                rows = await repo.find_by_parties(tokens, lo, hi, CourtLevel.SUPREME_COURT, limit=3)
        except DBAPIError:
            continue
        if len(rows) == 1 and rows[0].id not in (exclude or set()):
            hits[rows[0].id] += weight
    if not hits:
        return None
    (winner, weight), *rest = hits.most_common()
    if rest and rest[0][1] * 2 > weight:   # the names disagree on which record this is
        return None
    return Resolved(citation, winner, v.reporter, len(v.citing), v.names.most_common(1)[0][0][:300])


async def upsert(session: AsyncSession, found: list[Resolved], *, source: str = "mined") -> tuple[int, int]:
    """Write the resolved aliases: new rows, or more support for an existing mined row. Returns (added, updated)."""
    if not found:
        return 0, 0
    existing = {
        a.citation: a for a in (await session.execute(
            select(JudgmentAlias).where(JudgmentAlias.citation.in_([r.citation for r in found]))
        )).scalars().all()
    }
    added = updated = 0
    for r in found:
        row = existing.get(r.citation)
        if row is None:
            session.add(JudgmentAlias(judgment_id=r.judgment_id, citation=r.citation, reporter=r.reporter,
                                      source=source, support=r.support, case_name_as_cited=r.case_name_as_cited))
            added += 1
        elif row.source == "mined" and (row.judgment_id != r.judgment_id or row.support != r.support):
            row.judgment_id, row.support, row.case_name_as_cited = r.judgment_id, r.support, r.case_name_as_cited
            row.deleted_at = None
            updated += 1
    await session.flush()
    return added, updated


async def mine(session: AsyncSession, *, limit: int | None = None, batch: int = 200,
               min_support: int = 1, log=print) -> dict[str, int]:  # noqa: ANN001
    """Mine every Supreme Court judgment with text; returns counters."""
    repo = ResearchRepository(session)
    votes: dict[str, Votes] = {}
    ids = (await session.execute(
        select(Judgment.id).where(Judgment.court_level == CourtLevel.SUPREME_COURT, Judgment.full_text.is_not(None),
                                  Judgment.deleted_at.is_(None)).order_by(Judgment.judgment_date.desc().nulls_last())
    )).scalars().all()
    if limit:
        ids = ids[:limit]
    mentions = 0
    for start in range(0, len(ids), batch):
        rows = (await session.execute(
            select(Judgment.id, Judgment.full_text).where(Judgment.id.in_(ids[start:start + batch]))
        )).all()
        for jid, text in rows:
            mentions += collect(text or "", jid, votes)
        log(f"scanned {min(start + batch, len(ids))}/{len(ids)} judgments, {len(votes)} distinct citations, {mentions} mentions")
    resolved: list[Resolved] = []
    unresolved = 0
    for i, (citation, v) in enumerate(votes.items(), 1):
        if len(v.citing) < min_support:
            continue
        r = await resolve(repo, citation, v, exclude=v.citing)
        if r is None:
            unresolved += 1
        else:
            resolved.append(r)
        if i % 2000 == 0:
            log(f"resolved {len(resolved)} of {i} citations so far")
    added, updated = await upsert(session, resolved)
    return {"judgments": len(ids), "mentions": mentions, "distinct": len(votes), "resolved": len(resolved),
            "unresolved": unresolved, "added": added, "updated": updated}

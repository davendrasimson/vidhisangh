"""Data-access layer for the legal research corpus (global tables)."""

from __future__ import annotations

import html
import json
import re
import uuid
from dataclasses import astuple, dataclass
from datetime import date, timedelta

from sqlalchemy import String, cast, func, literal, literal_column, or_, select, text, tuple_
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.db_utils import LIKE_ESCAPE, contains
from app.core.exceptions import AppError
from app.modules.research.models import CaseCitation, CourtLevel, Judgment

# The generated tsvector (migration 0036) is not an ORM column — SQLite cannot
# hold it — so the PostgreSQL search path names it directly.
_SEARCH_VECTOR = literal_column("judgments.search_vector")
# Full text has its own GIN expression index (0040). This expression must be
# byte-identical to the index definition or the planner will not use it.
_FULL_TEXT_VECTOR = literal_column(
    "to_tsvector('english'::regconfig, left(coalesce(judgments.full_text, ''), 300000))"
)
_ENGLISH = literal_column("'english'::regconfig")
_CNR_RE = re.compile(r"^[A-Z]{4}[A-Z0-9]{2}\d{10}$", re.I)
# The single threshold for "small enough to treat precisely": below it a query
# is counted exactly and ranked by relevance; above it the total is an estimate
# and results come back newest-first. Counting is capped here, so this bounds
# the cost of every search. Measured on 5.6M rows: ranking 126k matches took
# 6.4 s, ranking 3k took 0.35 s.
_EXACT_COUNT_MAX = 25_000
# Newest-first fallback for broad queries searches this many recent years first.
RECENT_YEARS = 2
# Bound the facet aggregation. The sidebar is non-essential, so it is better to
# return no counts than to hold a worker long enough for nginx/gunicorn to 504.
_FACET_TIMEOUT_MS = 12_000
# The result page itself is bounded too (A-29): a pathological ranked query
# over a huge match set must fail as a 503 the client can retry narrower, not
# hold a worker until gunicorn kills it. Below the 60 s worker timeout and the
# 30 s session default so it fires first.
_SEARCH_TIMEOUT_MS = 20_000
_QUERY_CANCELED = "57014"


_MARK_RE = re.compile(r"</?mark>")


def _html_escape_sql(expr):  # noqa: ANN001, ANN202
    """``&`` → ``&amp;``, ``<`` → ``&lt;``, ``>`` → ``&gt;`` in SQL (order matters)."""
    expr = func.replace(expr, "&", "&amp;")
    expr = func.replace(expr, "<", "&lt;")
    return func.replace(expr, ">", "&gt;")


def sanitise_snippet(snippet: str | None) -> str | None:
    """Escape everything in a ``ts_headline`` snippet except our own
    ``<mark>``/``</mark>`` tags, so it is safe to render as HTML. The SQL side
    already escapes the source; this is the belt to that brace."""
    if not snippet:
        return snippet
    out: list[str] = []
    pos = 0
    for m in _MARK_RE.finditer(snippet):
        out.append(html.escape(snippet[pos:m.start()], quote=False))
        out.append(m.group(0))
        pos = m.end()
    out.append(html.escape(snippet[pos:], quote=False))
    return "".join(out)


class FacetsTimeout(Exception):
    """The facet aggregation exceeded its statement_timeout."""


class SearchTimeout(AppError):
    """The search itself exceeded its statement_timeout — surfaced as 503 with
    a hint to narrow the query rather than as an opaque 500."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "search_timeout"
    message = "The search took too long. Add a filter or a more specific phrase and try again."


def _is_query_canceled(exc: DBAPIError) -> bool:
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == _QUERY_CANCELED


@dataclass(slots=True)
class SearchFilters:
    """Everything a research query can be narrowed by. One object, so the
    result list, the total and the facet counts are guaranteed to agree."""

    query: str | None = None
    court_level: CourtLevel | None = None
    court: str | None = None
    case_type: str | None = None
    case_year: int | None = None
    judge: str | None = None
    advocate: str | None = None
    outcome: str | None = None
    act: str | None = None
    section: str | None = None
    year_from: int | None = None
    year_to: int | None = None

    def key(self) -> tuple:
        return astuple(self)


class ResearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def get(self, judgment_id: uuid.UUID) -> Judgment | None:
        res = await self.session.execute(
            select(Judgment).where(
                Judgment.id == judgment_id, Judgment.deleted_at.is_(None)
            )
        )
        return res.scalar_one_or_none()

    async def get_by_citation(self, citation: str) -> Judgment | None:
        res = await self.session.execute(
            select(Judgment).where(
                Judgment.citation == citation, Judgment.deleted_at.is_(None)
            )
        )
        return res.scalar_one_or_none()

    async def case_orders(self, cnr: str) -> list[Judgment]:
        """Every order the corpus holds for one case, oldest first."""
        res = await self.session.execute(
            select(Judgment)
            .where(Judgment.cnr_number == cnr, Judgment.deleted_at.is_(None))
            .order_by(Judgment.judgment_date.asc().nulls_last(), Judgment.created_at.asc())
        )
        return list(res.scalars().all())

    async def order_counts(self, cnrs: list[str]) -> dict[str, int]:
        """How many orders each of these cases has — for "1 of 7 orders" chips."""
        if not cnrs:
            return {}
        res = await self.session.execute(
            select(Judgment.cnr_number, func.count())
            .where(Judgment.cnr_number.in_(cnrs), Judgment.deleted_at.is_(None))
            .group_by(Judgment.cnr_number)
        )
        return {cnr: int(n) for cnr, n in res.all()}

    # ── Search ──────────────────────────────────────────────────────
    @property
    def _is_postgres(self) -> bool:
        return self.session.bind.dialect.name == "postgresql"

    def _conditions(self, f: SearchFilters) -> tuple[list, object | None]:
        """WHERE clauses for a filter set, plus the tsquery when FTS is in play.

        Shared by search and facets so the sidebar counts always describe the
        same result set the user is looking at.
        """
        conds: list = [Judgment.deleted_at.is_(None)]
        tsquery = None

        if f.query:
            q = f.query.strip()
            if self._is_postgres:
                # Google-style syntax: "exact phrase", -excluded, a OR b.
                # The config is a regconfig literal, not a bound string —
                # asyncpg would otherwise send it as text and Postgres refuses.
                tsquery = func.websearch_to_tsquery(_ENGLISH, q)
                # Two vectors, two GIN indexes, one BitmapOr: the registry
                # fields (title/judges/headnote) and the order's full text.
                matches = [
                    _SEARCH_VECTOR.op("@@")(tsquery),
                    _FULL_TEXT_VECTOR.op("@@")(tsquery),
                ]
                # A pasted CNR or "CRM-M/33310/2019" is an identifier, not prose;
                # FTS tokenises those badly, so match them literally as well.
                if _CNR_RE.match(q.replace("-", "").replace(" ", "")):
                    matches.append(Judgment.cnr_number == q.upper().replace("-", ""))
                if "/" in q:
                    matches.append(Judgment.case_name.ilike(contains(q), escape=LIKE_ESCAPE))
                conds.append(or_(*matches))
            else:  # SQLite (tests): substring fallback, no ranking
                like = contains(q)
                conds.append(
                    or_(
                        Judgment.case_name.ilike(like, escape=LIKE_ESCAPE),
                        Judgment.citation.ilike(like, escape=LIKE_ESCAPE),
                        Judgment.headnote.ilike(like, escape=LIKE_ESCAPE),
                        Judgment.full_text.ilike(like, escape=LIKE_ESCAPE),
                        Judgment.judge_text.ilike(like, escape=LIKE_ESCAPE),
                        cast(Judgment.keywords, String).ilike(like, escape=LIKE_ESCAPE),
                    )
                )

        if f.court_level is not None:
            conds.append(Judgment.court_level == f.court_level)
        if f.court:
            conds.append(Judgment.court == f.court)
        if f.case_type:
            conds.append(Judgment.case_type == f.case_type)
        if f.case_year is not None:
            conds.append(Judgment.case_year == f.case_year)
        if f.judge:
            conds.append(Judgment.judge_text.ilike(contains(f.judge), escape=LIKE_ESCAPE))
        if f.advocate:
            conds.append(Judgment.advocate_text.ilike(contains(f.advocate), escape=LIKE_ESCAPE))
        if f.outcome:
            conds.append(Judgment.outcome == f.outcome)
        if f.act:
            conds.append(cast(Judgment.acts, String).ilike(contains(f.act), escape=LIKE_ESCAPE))
        if f.section:
            conds.append(cast(Judgment.sections, String).ilike(contains(f.section), escape=LIKE_ESCAPE))
        if f.year_from is not None:
            conds.append(Judgment.judgment_date >= date(f.year_from, 1, 1))
        if f.year_to is not None:
            conds.append(Judgment.judgment_date <= date(f.year_to, 12, 31))
        return conds, tsquery

    async def _tune_txn(self, statement_timeout_ms: int = 0) -> None:
        """Tune this transaction for a heavy research query (Postgres only).

        - work_mem: a broad full-text query yields a bitmap of 100k+ rows; at
          the default work_mem it degrades to a *lossy* page-level bitmap and
          Postgres rechecks every row on every touched page — measured as 434k
          heap fetches for a 126k-row match.
        - statement_timeout: bounds a pathological aggregation (e.g. facets over
          a ~946k-match query, several seconds warm but far worse cold) so it
          fails as a catchable QueryCanceled rather than running until gunicorn
          SIGKILLs the worker at 60s and the user gets a 504. Callers that pass
          a timeout must handle DBAPIError and degrade gracefully.

        SET LOCAL lasts only for the current transaction.
        """
        if not self._is_postgres:
            return
        await self.session.execute(text("SET LOCAL work_mem = '96MB'"))
        if statement_timeout_ms:
            await self.session.execute(
                text(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
            )

    async def _page(self, stmt, limit: int, offset: int) -> list[tuple[Judgment, str | None]]:  # noqa: ANN001
        res = await self.session.execute(stmt.limit(limit).offset(offset))
        return [(row[0], row[1]) for row in res.all()]

    async def search(
        self, f: SearchFilters, *, limit: int, offset: int, rank: bool = True
    ) -> tuple[list[tuple[Judgment, str | None]], bool]:
        """Results with a highlighted snippet (PostgreSQL), ranked or newest-first.

        Returns (rows, windowed). `rank=False` is the path for very broad
        queries: ranking means computing ts_rank over *every* match before the
        top N can be chosen. Newest-first is cheaper, but the GIN index cannot
        return rows in date order either, so a date window is ANDed in first —
        it lets the planner intersect the date index with the text bitmap and
        touch only the recent slice (measured: 12.7k rows instead of 126k).
        If the window is too tight to fill the first page, it is dropped.
        """
        await self._tune_txn(statement_timeout_ms=_SEARCH_TIMEOUT_MS)
        try:
            return await self._search(f, limit=limit, offset=offset, rank=rank)
        except DBAPIError as exc:
            if _is_query_canceled(exc):
                raise SearchTimeout() from exc
            raise

    async def _search(
        self, f: SearchFilters, *, limit: int, offset: int, rank: bool
    ) -> tuple[list[tuple[Judgment, str | None]], bool]:
        conds, tsquery = self._conditions(f)
        newest_first = [Judgment.judgment_date.desc().nulls_last(), Judgment.created_at.desc()]

        if tsquery is None:
            stmt = select(Judgment, literal(None)).where(*conds).order_by(*newest_first)
            return await self._page(stmt, limit, offset), False

        # Highlight from the full text when we have it — that is where a phrase
        # from the order actually matched — else the registry description.
        # The source is HTML-escaped *before* ts_headline so the only markup in
        # the snippet is the <mark> we add (the text is user-curated, A-5);
        # ``sanitise_snippet`` re-checks the result in Python.
        snippet = func.ts_headline(
            _ENGLISH,
            _html_escape_sql(func.coalesce(Judgment.full_text, Judgment.headnote, Judgment.case_name)),
            tsquery,
            "StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=12, MaxFragments=2",
        )
        if rank:
            stmt = (
                select(Judgment, snippet)
                .where(*conds)
                .order_by(func.ts_rank_cd(_SEARCH_VECTOR, tsquery).desc(), *newest_first)
            )
            return await self._page(stmt, limit, offset), False

        recent = Judgment.judgment_date >= date.today() - timedelta(days=365 * RECENT_YEARS)
        stmt = select(Judgment, snippet).where(*conds, recent).order_by(*newest_first)
        rows = await self._page(stmt, limit, offset)
        if offset == 0 and len(rows) < limit:
            stmt = select(Judgment, snippet).where(*conds).order_by(*newest_first)
            return await self._page(stmt, limit, offset), False
        return rows, True

    async def count(self, f: SearchFilters) -> tuple[int, bool, bool]:
        """(total, is_estimate, is_lower_bound).

        The one decision that must be *exact* is "is this set small enough to
        rank?" (`_EXACT_COUNT_MAX`). Answering it does not need the true count —
        only whether the count exceeds the cap — so we count through a
        ``LIMIT cap+1`` subquery, which stops scanning as soon as the cap is
        passed. Cheap regardless of query breadth, and immune to the planner's
        unreliable multi-term estimates (it guesses 21k for a set that is really
        126k, because it assumes "anticipatory" and "bail" are independent).

        - At or below the cap: the capped count *is* the exact total.
        - Above the cap: return the planner estimate purely for display
          ("About 9,00,000"); the exact figure does not matter at that scale.
          When the planner's guess is itself below the cap we *know* it is
          wrong (we just counted past the cap), so report the cap as a lower
          bound — "More than 25,000" — rather than a misleading "About 21,000".
        """
        conds, _ = self._conditions(f)
        await self._tune_txn()  # work_mem persists for the search that follows

        capped_stmt = select(func.count()).select_from(
            select(literal(1)).where(*conds).limit(_EXACT_COUNT_MAX + 1).subquery()
        )
        capped = int((await self.session.execute(capped_stmt)).scalar_one())
        if capped <= _EXACT_COUNT_MAX:
            return capped, False, False
        if not self._is_postgres:
            return _EXACT_COUNT_MAX, True, True  # SQLite tests never reach this scale

        base = select(Judgment.id).where(*conds)
        compiled = base.compile(dialect=postgresql.dialect(paramstyle="named"))
        plan = (
            await self.session.execute(
                text("EXPLAIN (FORMAT JSON) " + str(compiled)), dict(compiled.params)
            )
        ).scalar_one()
        if isinstance(plan, str):
            plan = json.loads(plan)
        estimate = int(plan[0]["Plan"]["Plan Rows"])
        if estimate <= _EXACT_COUNT_MAX:
            return _EXACT_COUNT_MAX, True, True
        return estimate, True, False

    async def facets(
        self, f: SearchFilters, *, per_facet: int = 12, recent_only: bool = False
    ) -> dict[str, list[tuple[str, int]]]:
        """Top values per dimension for the current result set.

        `recent_only` mirrors the search's newest-first window for very broad
        queries, so the sidebar describes the same slice the list shows — and
        so the aggregation does not have to touch a million rows.
        """
        await self._tune_txn(statement_timeout_ms=_FACET_TIMEOUT_MS)
        conds, _ = self._conditions(f)
        if recent_only:
            conds.append(
                Judgment.judgment_date >= date.today() - timedelta(days=365 * RECENT_YEARS)
            )
        year = func.extract("year", Judgment.judgment_date)
        plain = {
            "courts": Judgment.court,
            "years": year,
            "case_types": Judgment.case_type,
            "outcomes": Judgment.outcome,
        }
        out: dict[str, list[tuple[str, int]]] = {}

        if self._is_postgres:
            try:
                return await self._facets_pg(conds, plain, per_facet)
            except DBAPIError as exc:
                # statement_timeout cancels as QueryCanceled (SQLSTATE 57014);
                # surface as a typed signal so the service returns empty facets
                # rather than a 500. Any other DB error is a real bug — re-raise.
                if _is_query_canceled(exc):
                    raise FacetsTimeout from exc
                raise

        # SQLite (tests): no GROUPING SETS or unnest — one GROUP BY per dimension.
        return await self._facets_sqlite(conds, plain, per_facet)

    async def _facets_pg(self, conds, plain, per_facet):  # noqa: ANN001
        out: dict[str, list[tuple[str, int]]] = {}
        # One heap pass for all four plain dimensions via GROUPING SETS
        # instead of one full scan per dimension — five separate GROUP BYs
        # over a 946k-row match set measured 41 s; this is the fix.
        cols = list(plain.values())
        stmt = (
            select(*cols, func.count())
            .where(*conds)
            .group_by(func.grouping_sets(*[tuple_(c) for c in cols]))
        )
        buckets: dict[str, list[tuple[str, int]]] = {name: [] for name in plain}
        for row in (await self.session.execute(stmt)).all():
            values, n = row[:-1], int(row[-1])
            # Exactly one column is non-NULL per row: the dimension grouped on.
            for name, value in zip(plain, values):
                if value is None or value == "":
                    continue
                buckets[name].append((str(int(value)) if name == "years" else str(value), n))
                break
        for name, items in buckets.items():
            # Years read best newest-first; everything else by frequency.
            if name == "years":
                items.sort(key=lambda t: int(t[0]), reverse=True)
            else:
                items.sort(key=lambda t: (-t[1], t[0]))
            out[name] = items[:per_facet]

        # judge_text holds a whole bench ("A | B"). Facet per *judge*, so
        # someone who sat on many benches is one value, not many.
        bench_member = (
            select(func.unnest(func.string_to_array(Judgment.judge_text, " | ")).label("name"))
            .where(*conds, Judgment.judge_text.isnot(None))
            .subquery()
        )
        stmt = (
            select(bench_member.c.name, func.count())
            .where(bench_member.c.name != "")
            .group_by(bench_member.c.name)
            .order_by(func.count().desc(), bench_member.c.name)
            .limit(per_facet)
        )
        out["judges"] = [(str(v), int(n)) for v, n in (await self.session.execute(stmt)).all()]

        # Same shape for advocates: advocate_text holds everyone on the record.
        on_record = (
            select(func.unnest(func.string_to_array(Judgment.advocate_text, " | ")).label("name"))
            .where(*conds, Judgment.advocate_text.isnot(None))
            .subquery()
        )
        stmt = (
            select(on_record.c.name, func.count())
            .where(on_record.c.name != "")
            .group_by(on_record.c.name)
            .order_by(func.count().desc(), on_record.c.name)
            .limit(per_facet)
        )
        out["advocates"] = [(str(v), int(n)) for v, n in (await self.session.execute(stmt)).all()]
        return out

    async def _facets_sqlite(self, conds, plain, per_facet):  # noqa: ANN001
        # SQLite (tests): no GROUPING SETS or unnest — one GROUP BY per dimension.
        out: dict[str, list[tuple[str, int]]] = {}
        for name, column in {
            **plain, "judges": Judgment.judge_text, "advocates": Judgment.advocate_text
        }.items():
            present = (
                [Judgment.judgment_date.isnot(None)]
                if name == "years"
                else [column.isnot(None), column != ""]
            )
            order = [column.desc()] if name == "years" else [func.count().desc(), column]
            stmt = (
                select(column, func.count())
                .where(*conds, *present)
                .group_by(column)
                .order_by(*order)
                .limit(per_facet)
            )
            rows = (await self.session.execute(stmt)).all()
            out[name] = [(str(int(v)) if name == "years" else str(v), int(n)) for v, n in rows]
        return out

    # ── Citation graph ──────────────────────────────────────────────
    async def outgoing(
        self, judgment_id: uuid.UUID
    ) -> list[tuple[CaseCitation, Judgment | None]]:
        res = await self.session.execute(
            select(CaseCitation, Judgment)
            .outerjoin(Judgment, Judgment.id == CaseCitation.to_judgment_id)
            .where(CaseCitation.from_judgment_id == judgment_id)
        )
        return [(row[0], row[1]) for row in res.all()]

    async def incoming(
        self, judgment_id: uuid.UUID
    ) -> list[tuple[CaseCitation, Judgment]]:
        res = await self.session.execute(
            select(CaseCitation, Judgment)
            .join(Judgment, Judgment.id == CaseCitation.from_judgment_id)
            .where(CaseCitation.to_judgment_id == judgment_id)
        )
        return [(row[0], row[1]) for row in res.all()]

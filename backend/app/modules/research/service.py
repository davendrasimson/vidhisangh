"""Legal research service — corpus management, search, citation graph."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.research.models import CaseCitation, CourtLevel, Judgment
from app.modules.research.normalise import (
    advocate_text,
    normalise_judges,
    parse_counsel,
    parse_neutral_citation,
    parse_registry_title,
    split_parties,
)
from app.modules.research.repository import (
    RECENT_YEARS,
    FacetsTimeout,
    ResearchRepository,
    SearchFilters,
)
from app.modules.research.schemas import (
    CaseOrder,
    CaseRead,
    CitationCreate,
    CitationEdge,
    CitationGraph,
    FacetBucket,
    JudgmentCreate,
    SearchFacets,
)

# Process-local TTL cache for counts and facets over the (global) corpus.
# Keyed by the full filter tuple, so two users with the same query share it and
# nothing tenant-specific is ever stored here.
_CACHE_TTL_SECONDS = 300
_CACHE_MAX_ENTRIES = 512
_cache: dict[tuple, tuple[float, object]] = {}


def _cache_get(key: tuple):  # noqa: ANN202
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    _cache.pop(key, None)
    return None


def _cache_put(key: tuple, value: object, ttl: float = _CACHE_TTL_SECONDS) -> None:
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        _cache.clear()  # crude, but bounded and never stale-forever
    _cache[key] = (time.monotonic() + ttl, value)


# The landing page (no query, no filters) aggregates the most rows and changes
# only when a court is loaded; keep it for an hour so it is not recomputed
# under bulk-ingest load, where it can exceed the facet timeout.
_LANDING_TTL_SECONDS = 3600


def _ttl_for(filters: SearchFilters) -> float:
    return _LANDING_TTL_SECONDS if filters == SearchFilters() else _CACHE_TTL_SECONDS


class ResearchService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.repo = ResearchRepository(session)

    async def _require(self, judgment_id: uuid.UUID) -> Judgment:
        judgment = await self.repo.get(judgment_id)
        if judgment is None:
            raise NotFoundError("Judgment not found.")
        return judgment

    async def add_judgment(self, data: JudgmentCreate) -> Judgment:
        if await self.repo.get_by_citation(data.citation) is not None:
            raise ConflictError("A judgment with this citation already exists.")
        # Same derivations the bulk backfill applies, so API-added judgments
        # facet and filter identically to loaded ones.
        title = parse_registry_title(data.case_name, data.judgment_date)
        petitioner, respondent = split_parties(title.cause_title)
        pet_adv, resp_adv = parse_counsel(data.headnote)
        judgment = Judgment(
            case_name=data.case_name,
            citation=data.citation,
            neutral_citation=data.neutral_citation or parse_neutral_citation(data.headnote),
            cnr_number=data.cnr_number.upper() if data.cnr_number else None,
            court=data.court,
            court_level=data.court_level,
            bench=data.bench,
            judges=data.judges,
            judge_text=normalise_judges(data.judges),
            case_type=title.case_type,
            case_number=title.case_number,
            case_year=title.case_year,
            cause_title=title.cause_title,
            petitioner=petitioner,
            respondent=respondent,
            petitioner_advocates=pet_adv,
            respondent_advocates=resp_adv,
            advocate_text=advocate_text(pet_adv, resp_adv),
            judgment_date=data.judgment_date,
            acts=data.acts,
            sections=data.sections,
            keywords=data.keywords,
            headnote=data.headnote,
            outcome=data.outcome,
            url=data.url,
            full_text=data.full_text,
            text_extracted_at=datetime.now(UTC) if data.full_text else None,
            added_by=self.user_id,
        )
        self.repo.add(judgment)
        await self.session.flush()
        return judgment

    async def get_judgment(self, judgment_id: uuid.UUID) -> Judgment:
        return await self._require(judgment_id)

    async def search(
        self, filters: SearchFilters, *, limit: int, offset: int
    ) -> tuple[list[tuple[Judgment, str | None]], int, bool, bool, bool, bool]:
        """One page of results, the total (exact or estimated), and flags.

        Returns (rows, total, total_is_estimate, total_is_lower_bound, ranked,
        windowed). Relevance ranking is only applied when the match set is
        small enough to rank in interactive time (see `_EXACT_COUNT_MAX`);
        beyond that, results come back newest-first from the most recent
        years, and the UI says so.
        """
        total, is_estimate, lower_bound = await self._cached_count(filters)
        # `is_estimate` is set exactly when the capped count passed the cap, so
        # it is the reliable signal for "too big to rank" — the total itself is
        # not, since a planner estimate can read low for a huge set.
        ranked = bool(filters.query) and not is_estimate
        rows, windowed = await self.repo.search(filters, limit=limit, offset=offset, rank=ranked)
        return rows, total, is_estimate, lower_bound, ranked, windowed

    async def facets(self, filters: SearchFilters) -> SearchFacets:
        """Sidebar counts. Cached briefly: the corpus is a shared, slowly
        changing reference library, and a broad query (or none) aggregates over
        millions of rows, so recomputing it per keystroke would be wasteful."""
        key = ("facets", *filters.key())
        cached = _cache_get(key)
        if cached is not None:
            return cached
        total, is_estimate, lower_bound = await self._cached_count(filters)
        # Any set too large to count exactly is faceted over the most recent
        # years only — including the landing page (no query: 5.6M rows, a full
        # scan blows the 12 s timeout; the 2-year slice of ~1M rows takes
        # ~1.6 s). The response says so via `recent_years`.
        recent_only = is_estimate
        try:
            raw = await self.repo.facets(filters, recent_only=recent_only)
        except FacetsTimeout:
            # The sidebar is non-essential; a query so broad the aggregation
            # times out still returns its total and its (working) result list.
            # The `facets_partial` flag tells the UI to say so.
            facets = SearchFacets(
                total=total, total_is_estimate=is_estimate,
                total_is_lower_bound=lower_bound,
                recent_years=RECENT_YEARS if recent_only else None,
                facets_partial=True,
            )
            _cache_put(key, facets)
            return facets
        facets = SearchFacets(
            total=total,
            total_is_estimate=is_estimate,
            total_is_lower_bound=lower_bound,
            recent_years=RECENT_YEARS if recent_only else None,
            **{name: [FacetBucket(value=v, count=n) for v, n in buckets]
               for name, buckets in raw.items()},
        )
        _cache_put(key, facets, ttl=_ttl_for(filters))  # a timed-out (partial) result keeps the short TTL
        return facets

    async def case(self, cnr: str) -> CaseRead:
        """One case (CNR) assembled from all its orders.

        Header fields come from the latest order that has them — the registry
        title can be re-entered between hearings; the newest form is the one
        the parties currently use. Counsel and judges are the union across
        orders, since both change over a case's life.
        """
        orders = await self.repo.case_orders(cnr)
        if not orders:
            raise NotFoundError("No orders for this CNR in the library.")
        newest = orders[-1]

        def first(attr: str):  # noqa: ANN202 — latest order with a value
            return next((getattr(o, attr) for o in reversed(orders) if getattr(o, attr)), None)

        def union(attr: str) -> list[str]:
            seen: list[str] = []
            for o in orders:
                for name in getattr(o, attr) or []:
                    if name not in seen:
                        seen.append(name)
            return seen

        judges: list[str] = []
        for o in orders:
            for name in (o.judge_text or "").split(" | "):
                if name and name not in judges:
                    judges.append(name)

        return CaseRead(
            cnr_number=cnr,
            court=newest.court,
            court_level=newest.court_level,
            case_type=first("case_type"),
            case_number=first("case_number"),
            case_year=first("case_year"),
            cause_title=first("cause_title") or newest.case_name,
            petitioner=first("petitioner"),
            respondent=first("respondent"),
            petitioner_advocates=union("petitioner_advocates"),
            respondent_advocates=union("respondent_advocates"),
            judge_names=judges,
            filed_on=min((o.filed_on for o in orders if o.filed_on), default=None),
            first_order_on=orders[0].judgment_date,
            latest_order_on=newest.judgment_date,
            latest_outcome=first("outcome"),
            orders=[CaseOrder.from_orm_row(o) for o in orders],
        )

    async def order_counts(self, rows: list[tuple[Judgment, str | None]]) -> dict[str, int]:
        cnrs = sorted({j.cnr_number for j, _ in rows if j.cnr_number})
        return await self.repo.order_counts(cnrs)

    async def _cached_count(self, filters: SearchFilters) -> tuple[int, bool, bool]:
        key = ("count", *filters.key())
        cached = _cache_get(key)
        if cached is None:
            cached = await self.repo.count(filters)
            _cache_put(key, cached, ttl=_ttl_for(filters))
        return cached

    async def add_citation(
        self, from_judgment_id: uuid.UUID, data: CitationCreate
    ) -> CaseCitation:
        await self._require(from_judgment_id)
        if data.to_judgment_id is None and not data.external_citation:
            raise ValidationError("Provide either a target judgment or an external citation.")
        if data.to_judgment_id is not None:
            if data.to_judgment_id == from_judgment_id:
                raise ValidationError("A judgment cannot cite itself.")
            await self._require(data.to_judgment_id)
        citation = CaseCitation(
            from_judgment_id=from_judgment_id,
            to_judgment_id=data.to_judgment_id,
            external_citation=data.external_citation,
            relationship_type=data.relationship_type,
            added_by=self.user_id,
        )
        self.repo.add(citation)
        await self.session.flush()
        return citation

    async def citation_graph(self, judgment_id: uuid.UUID) -> CitationGraph:
        await self._require(judgment_id)
        cites: list[CitationEdge] = []
        for edge, target in await self.repo.outgoing(judgment_id):
            if target is not None:
                cites.append(
                    CitationEdge(
                        id=edge.id,
                        relationship_type=edge.relationship_type,
                        judgment_id=target.id,
                        case_name=target.case_name,
                        citation=target.citation,
                    )
                )
            elif edge.external_citation:
                cites.append(
                    CitationEdge(
                        id=edge.id,
                        relationship_type=edge.relationship_type,
                        citation=edge.external_citation,
                    )
                )

        cited_by: list[CitationEdge] = [
            CitationEdge(
                id=edge.id,
                relationship_type=edge.relationship_type,
                judgment_id=source.id,
                case_name=source.case_name,
                citation=source.citation,
            )
            for edge, source in await self.repo.incoming(judgment_id)
        ]
        return CitationGraph(cites=cites, cited_by=cited_by)

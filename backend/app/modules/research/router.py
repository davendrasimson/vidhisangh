"""Legal research HTTP endpoints — corpus, search, citation graph.

Gated by ``research:use``. The corpus is a shared, cross-tenant reference
library, so a plain (RLS-scoped) session is used but no tenant filter applies.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.pagination import PageParams, page_params
from app.modules.research.models import CourtLevel
from app.modules.research.repository import RECENT_YEARS, SearchFilters
from app.modules.research.schemas import (
    CaseRead,
    CitationCreate,
    CitationGraph,
    JudgmentCreate,
    JudgmentRead,
    JudgmentSummary,
    SearchFacets,
    SearchPage,
)
from app.modules.research.service import ResearchService

router = APIRouter(
    prefix="/research",
    tags=["Legal Research"],
    dependencies=[require_permission("research:use")],
)

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> ResearchService:
    return ResearchService(session, current.id)


@router.post(
    "/judgments",
    response_model=JudgmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a judgment to the research library",
)
async def add_judgment(
    data: JudgmentCreate, current: CurrentUserDep, session: TenantSessionDep
) -> JudgmentRead:
    judgment = await _svc(current, session).add_judgment(data)
    return JudgmentRead.from_orm_row(judgment)


def _filters(
    q: Annotated[str | None, Query(max_length=300)] = None,
    court_level: Annotated[CourtLevel | None, Query()] = None,
    court: Annotated[str | None, Query(max_length=200)] = None,
    case_type: Annotated[str | None, Query(max_length=40)] = None,
    case_year: Annotated[int | None, Query(ge=1800, le=2200)] = None,
    judge: Annotated[str | None, Query(max_length=200)] = None,
    advocate: Annotated[str | None, Query(max_length=200)] = None,
    outcome: Annotated[str | None, Query(max_length=300)] = None,
    act: Annotated[str | None, Query(max_length=200)] = None,
    section: Annotated[str | None, Query(max_length=100)] = None,
    year_from: Annotated[int | None, Query(ge=1800, le=2200)] = None,
    year_to: Annotated[int | None, Query(ge=1800, le=2200)] = None,
) -> SearchFilters:
    return SearchFilters(
        query=q or None, court_level=court_level, court=court or None,
        case_type=case_type or None, case_year=case_year, judge=judge or None,
        advocate=advocate or None,
        outcome=outcome or None, act=act or None, section=section or None,
        year_from=year_from, year_to=year_to,
    )


Filters = Annotated[SearchFilters, Depends(_filters)]


@router.get(
    "/judgments",
    response_model=SearchPage,
    summary="Search the research library",
    description=(
        "Ranked full-text search. `q` accepts Google-style syntax: quotes for an "
        "exact phrase, `-word` to exclude, `a OR b`. A CNR or a case number like "
        "`CRM-M/33310/2019` is matched literally as well. Narrow with `court`, "
        "`case_type`, `case_year`, `judge`, `outcome` — the values the facets "
        "endpoint reports."
    ),
)
async def search_judgments(
    page: Pagination, filters: Filters, current: CurrentUserDep, session: TenantSessionDep
) -> SearchPage:
    svc = _svc(current, session)
    rows, total, is_estimate, lower_bound, ranked, windowed = await svc.search(
        filters, limit=page.size, offset=page.offset
    )
    counts = await svc.order_counts(rows)
    items = []
    for j, snippet in rows:
        item = JudgmentSummary.from_orm_row(j, snippet)
        item.order_count = counts.get(j.cnr_number) if j.cnr_number else None
        items.append(item)
    return SearchPage(
        items=items,
        total=total,
        total_is_estimate=is_estimate,
        total_is_lower_bound=lower_bound,
        page=page.page,
        size=page.size,
        ranked=ranked,
        recent_years=RECENT_YEARS if windowed else None,
    )


@router.get(
    "/cases/{cnr}",
    response_model=CaseRead,
    summary="A case (CNR) with every order the library holds for it",
    description=(
        "The corpus lists orders; a case has many. This groups them: parties, "
        "counsel, judges, filing date and each order in date order."
    ),
)
async def get_case(
    cnr: Annotated[str, Path(min_length=10, max_length=20)],
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> CaseRead:
    return await _svc(current, session).case(cnr.upper())


# Declared before `/judgments/{judgment_id}` so "facets" is not read as an id.
@router.get(
    "/judgments/facets",
    response_model=SearchFacets,
    summary="Counts by court, year, case type, judge and outcome for a query",
)
async def judgment_facets(
    filters: Filters, current: CurrentUserDep, session: TenantSessionDep
) -> SearchFacets:
    return await _svc(current, session).facets(filters)


@router.get(
    "/judgments/{judgment_id}",
    response_model=JudgmentRead,
    summary="Judgment detail",
)
async def get_judgment(
    judgment_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> JudgmentRead:
    judgment = await _svc(current, session).get_judgment(judgment_id)
    return JudgmentRead.from_orm_row(judgment)


@router.post(
    "/judgments/{judgment_id}/citations",
    status_code=status.HTTP_201_CREATED,
    summary="Record a citation from this judgment",
)
async def add_citation(
    judgment_id: uuid.UUID,
    data: CitationCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> dict:
    citation = await _svc(current, session).add_citation(judgment_id, data)
    return {"id": str(citation.id)}


@router.get(
    "/judgments/{judgment_id}/citations",
    response_model=CitationGraph,
    summary="Citation graph (cites & cited-by)",
)
async def citation_graph(
    judgment_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> CitationGraph:
    return await _svc(current, session).citation_graph(judgment_id)

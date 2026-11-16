from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.modules.brief import service
from app.modules.brief.schemas import BriefRead, QuizAnswerIn, QuizAnswerRead
from app.modules.courts import service as courts
from app.modules.network.schemas import DirectoryPerson
from app.modules.network.service import NetworkService
from app.modules.profile.models import ProfessionalProfile

router = APIRouter(prefix="/brief", tags=["daily brief"])


def _people(rows) -> list[DirectoryPerson]:  # noqa: ANN001
    out = []
    for identity, conn_status, following in rows:
        person = DirectoryPerson.model_validate(identity)
        person.connection_status = conn_status
        person.is_following = following
        out.append(person)
    return out


@router.get(
    "", dependencies=[require_permission("post:read")], response_model=BriefRead,
    summary="VidhiSangh Daily: today's section, judgment, question, landmark, news and fraternity",
)
async def brief(
    current: CurrentUserDep, session: TenantSessionDep,
    day: date | None = Query(default=None, description="Defaults to today in India"),
    source: str | None = Query(default=None, alias="from", max_length=20,
                               description="push or whatsapp when opened from the morning message"),
) -> BriefRead:
    today = service.today_ist()
    day = day or today
    if day > today:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That day's brief is not out yet.")
    data = await service.compose(session, day, current.id)
    fraternity = None
    if current.tenant_id is not None:
        home = await NetworkService(session, current.id, current.tenant_id).home(limit=3)
        people = _people(home["nearby"]) or _people(home["recent"])
        fraternity = {"members": home["members"], "in_city": home["in_city"], "joined_7d": home["joined_7d"],
                      "city": home["city"], "people": people[:3]}
    # The member's own profile picks the court card; nothing about them leaves the app.
    profile = await session.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == current.id))
    court = courts.court_for_profile(profile)
    court_card = await courts.card_for(session, court, day) if court else None
    if day == today:
        await service.mark_opened(session, current.id, day, source if source in ("push", "whatsapp") else "app")
    return BriefRead.model_validate({**data, "fraternity": fraternity, "court": court_card})


@router.post(
    "/quiz/{quiz_id}/answer", dependencies=[require_permission("post:read")], response_model=QuizAnswerRead,
    summary="Answer today's question (one attempt; the answer and explanation come back)",
)
async def answer(quiz_id: str, body: QuizAnswerIn, current: CurrentUserDep, session: TenantSessionDep) -> QuizAnswerRead:
    result = await service.answer_quiz(session, current.id, quiz_id, body.chosen, service.today_ist())
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such question.")
    return QuizAnswerRead.model_validate(result)

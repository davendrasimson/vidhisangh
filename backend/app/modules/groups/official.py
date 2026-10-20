"""The official community groups, so the Groups page is never empty.

Owned by the official VidhiSangh account (``network.official.OFFICIAL_AUTHOR_ID``),
public and verified, each with a starter post. Platform admins (superusers)
are made group admins so a real person can moderate. ``seed`` is idempotent:
it adds what is missing (by slug) and never changes or removes a group.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.groups.models import (
    Group,
    GroupMembership,
    GroupPost,
    GroupType,
    GroupVisibility,
    MemberRole,
    MemberStatus,
)
from app.modules.identity.models import User
from app.modules.network.official import OFFICIAL_AUTHOR_ID, OFFICIAL_NAME


@dataclass(frozen=True)
class OfficialGroup:
    slug: str
    name: str
    description: str
    starter: str


GROUPS: tuple[OfficialGroup, ...] = (
    OfficialGroup("ask-a-senior", "Ask a Senior",
        "Questions on practice, procedure and the profession, answered by experienced members. No question is too basic.",
        "Welcome! Seniors: what is one thing you wish you had known in your first year of practice? "
        "Juniors and students: ask anything about drafting, filing, court craft or building a practice."),
    OfficialGroup("new-criminal-laws", "New Criminal Laws (BNS · BNSS · BSA)",
        "Practice under the Bharatiya Nyaya Sanhita, Nagarik Suraksha Sanhita and Sakshya Adhiniyam: changes from the IPC, CrPC and Evidence Act, transition questions and early judgments.",
        "Which change in the BNS, BNSS or BSA has affected your practice the most so far? "
        "Tip: the IPC to BNS converter at vidhisangh.com/acts/ipc-to-bns/ finds the new section for any old one."),
    OfficialGroup("judicial-services-aspirants", "Judicial Services Aspirants",
        "Preparing for the civil judge / judicial magistrate and HJS examinations: syllabus, answer writing, interviews and notifications.",
        "Which State judicial services examination are you preparing for, and what is the hardest part of your preparation?"),
    OfficialGroup("law-students", "Law Students",
        "Moots, internships, research, placements and the first steps into practice.",
        "Introduce yourself: your law school, year, and the area of law you would like to practise in."),
    OfficialGroup("women-in-law", "Women in Law",
        "A community for women advocates, judges, academics and students: mentoring, opportunities and experiences.",
        "Welcome! Share an opportunity, a mentor who helped you, or a question you would like this community to discuss."),
    OfficialGroup("corporate-in-house-counsel", "Corporate & In-house Counsel",
        "Contracts, compliance, disputes and working with outside counsel, for in-house teams and corporate lawyers.",
        "What is the one compliance change of this year that kept your legal team busiest?"),
    OfficialGroup("supreme-court-of-india", "Supreme Court of India",
        "For advocates practising before the Supreme Court: listings, procedure, AOR matters and recent judgments.",
        "Share a practice tip for first-time appearances before the Supreme Court."),
    OfficialGroup("delhi-high-court", "Delhi High Court",
        "Members practising before the Delhi High Court and Delhi district courts: rosters, notices and practice questions.",
        "Welcome to the Delhi High Court group. Which bench or roster change should everyone know about this week?"),
    OfficialGroup("punjab-and-haryana-high-court", "Punjab & Haryana High Court",
        "Members practising before the Punjab and Haryana High Court and the district courts of Punjab, Haryana and Chandigarh.",
        "Welcome! Introduce yourself and the courts where you usually appear."),
    OfficialGroup("allahabad-high-court", "Allahabad High Court",
        "Members practising before the Allahabad High Court (Allahabad and Lucknow) and the district courts of Uttar Pradesh.",
        "Welcome! Introduce yourself and the courts where you usually appear."),
    OfficialGroup("bombay-high-court", "Bombay High Court",
        "Members practising before the Bombay High Court (Mumbai, Nagpur, Aurangabad, Goa) and the courts of Maharashtra and Goa.",
        "Welcome! Introduce yourself and the courts where you usually appear."),
    OfficialGroup("madras-high-court", "Madras High Court",
        "Members practising before the Madras High Court (Chennai and Madurai) and the courts of Tamil Nadu and Puducherry.",
        "Welcome! Introduce yourself and the courts where you usually appear."),
    OfficialGroup("karnataka-high-court", "Karnataka High Court",
        "Members practising before the Karnataka High Court (Bengaluru, Dharwad, Kalaburagi) and the courts of Karnataka.",
        "Welcome! Introduce yourself and the courts where you usually appear."),
    OfficialGroup("calcutta-high-court", "Calcutta High Court",
        "Members practising before the Calcutta High Court and the courts of West Bengal and the Andaman and Nicobar Islands.",
        "Welcome! Introduce yourself and the courts where you usually appear."),
)


async def seed(session: AsyncSession) -> dict[str, int]:
    """Create the missing official groups; make platform admins group admins. Needs RLS bypass (reads users)."""
    admins = (await session.scalars(
        select(User).where(User.is_superuser.is_(True), User.is_active.is_(True), User.deleted_at.is_(None))
    )).all()
    report = {"groups": 0, "admins": 0}
    for spec in GROUPS:
        group = await session.scalar(select(Group).where(Group.slug == spec.slug, Group.deleted_at.is_(None)))
        if group is None:
            group = Group(slug=spec.slug, name=spec.name, description=spec.description, group_type=GroupType.COMMUNITY,
                          visibility=GroupVisibility.PUBLIC, owner_id=OFFICIAL_AUTHOR_ID, is_verified=True,
                          member_count=1, post_count=1)
            session.add(group)
            await session.flush()
            session.add(GroupMembership(group_id=group.id, user_id=OFFICIAL_AUTHOR_ID, member_name=OFFICIAL_NAME,
                                        role=MemberRole.OWNER, status=MemberStatus.ACTIVE))
            session.add(GroupPost(group_id=group.id, author_id=OFFICIAL_AUTHOR_ID, author_name=OFFICIAL_NAME,
                                  content=spec.starter))
            report["groups"] += 1
        for admin in admins:
            existing = await session.scalar(select(GroupMembership).where(
                GroupMembership.group_id == group.id, GroupMembership.user_id == admin.id))
            if existing is None:
                session.add(GroupMembership(group_id=group.id, user_id=admin.id, member_name=admin.full_name,
                                            role=MemberRole.ADMIN, status=MemberStatus.ACTIVE))
                group.member_count += 1
                report["admins"] += 1
        await session.flush()
    return report

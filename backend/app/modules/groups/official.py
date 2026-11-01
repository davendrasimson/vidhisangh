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
    # Added 1 Nov 2026 so every High Court bar has a room before the invitations reach it.
    *(OfficialGroup(slug, name, f"Members practising before the {name} and the district courts of {region}.",
                    "Welcome! Introduce yourself and the courts where you usually appear.")
      for slug, name, region in (
          ("gujarat-high-court", "Gujarat High Court", "Gujarat"),
          ("rajasthan-high-court", "Rajasthan High Court", "Rajasthan (Jodhpur and Jaipur)"),
          ("madhya-pradesh-high-court", "Madhya Pradesh High Court", "Madhya Pradesh (Jabalpur, Indore and Gwalior)"),
          ("chhattisgarh-high-court", "Chhattisgarh High Court", "Chhattisgarh"),
          ("patna-high-court", "Patna High Court", "Bihar"),
          ("jharkhand-high-court", "Jharkhand High Court", "Jharkhand"),
          ("orissa-high-court", "Orissa High Court", "Odisha"),
          ("telangana-high-court", "Telangana High Court", "Telangana"),
          ("andhra-pradesh-high-court", "Andhra Pradesh High Court", "Andhra Pradesh"),
          ("kerala-high-court", "Kerala High Court", "Kerala and Lakshadweep"),
          ("gauhati-high-court", "Gauhati High Court", "Assam, Nagaland, Mizoram and Arunachal Pradesh"),
          ("jammu-kashmir-ladakh-high-court", "High Court of J&K and Ladakh", "Jammu & Kashmir and Ladakh"),
          ("himachal-pradesh-high-court", "Himachal Pradesh High Court", "Himachal Pradesh"),
          ("uttarakhand-high-court", "Uttarakhand High Court", "Uttarakhand"),
          ("tripura-high-court", "Tripura High Court", "Tripura"),
          ("meghalaya-high-court", "Meghalaya High Court", "Meghalaya"),
          ("manipur-high-court", "Manipur High Court", "Manipur"),
          ("sikkim-high-court", "Sikkim High Court", "Sikkim"),
      )),
)

# Which official group a court name (as written on the public lists the invitations come from, or on a
# member's profile) belongs to. Checked in order; the first keyword found wins.
COURT_GROUPS: tuple[tuple[str, str], ...] = (
    ("supreme court", "supreme-court-of-india"),
    ("delhi", "delhi-high-court"),
    ("punjab", "punjab-and-haryana-high-court"), ("haryana", "punjab-and-haryana-high-court"), ("chandigarh", "punjab-and-haryana-high-court"),
    ("allahabad", "allahabad-high-court"), ("lucknow", "allahabad-high-court"), ("uttar pradesh", "allahabad-high-court"),
    ("bombay", "bombay-high-court"), ("maharashtra", "bombay-high-court"), ("goa", "bombay-high-court"),
    ("madras", "madras-high-court"), ("tamil nadu", "madras-high-court"),
    ("karnataka", "karnataka-high-court"),
    ("calcutta", "calcutta-high-court"), ("west bengal", "calcutta-high-court"),
    ("gujarat", "gujarat-high-court"),
    ("rajasthan", "rajasthan-high-court"),
    ("madhya pradesh", "madhya-pradesh-high-court"),
    ("chhattisgarh", "chhattisgarh-high-court"),
    ("patna", "patna-high-court"), ("bihar", "patna-high-court"),
    ("jharkhand", "jharkhand-high-court"),
    ("orissa", "orissa-high-court"), ("odisha", "orissa-high-court"),
    ("telangana", "telangana-high-court"), ("hyderabad", "telangana-high-court"),
    ("andhra", "andhra-pradesh-high-court"),
    ("kerala", "kerala-high-court"),
    ("gauhati", "gauhati-high-court"), ("assam", "gauhati-high-court"),
    ("kashmir", "jammu-kashmir-ladakh-high-court"), ("ladakh", "jammu-kashmir-ladakh-high-court"), ("jammu", "jammu-kashmir-ladakh-high-court"),
    ("himachal", "himachal-pradesh-high-court"),
    ("uttarakhand", "uttarakhand-high-court"),
    ("tripura", "tripura-high-court"),
    ("meghalaya", "meghalaya-high-court"),
    ("manipur", "manipur-high-court"),
    ("sikkim", "sikkim-high-court"),
)


def court_group_slug(court: str | None) -> str | None:
    """The official group for a court name ('Allahabad High Court, Lucknow Bench' → allahabad-high-court)."""
    text = (court or "").lower()
    return next((slug for key, slug in COURT_GROUPS if key in text), None) if text else None


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

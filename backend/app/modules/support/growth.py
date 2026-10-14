"""Registration growth for the platform admin: daily / weekly / monthly sign-ups.

Counted in India time (a sign-up at 00:30 IST belongs to that day, not the
previous UTC day). Numbers are small at launch, so every figure also carries
the comparison period, cumulative totals and the next milestone.

Members = users not deleted and not platform administrators. A member is a
"self sign-up" when their organisation was created with them (within two
minutes); otherwise a firm added them to its team.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import OAuthIdentity, User
from app.modules.profile.masters import PROFILE_MASTERS
from app.modules.profile.models import ProfessionalProfile
from app.modules.referrals.models import Referral
from app.modules.tenancy.models import Tenant

IST = ZoneInfo("Asia/Kolkata")
MILESTONES = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000)
METHOD_LABELS = {"whatsapp": "WhatsApp", "email": "Email", "google": "Google", "team": "Added by a firm"}
ROLE_LABELS = {r["value"]: r["label"] for r in PROFILE_MASTERS["professional_roles"]}


def _ist(value: datetime) -> datetime:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(IST)


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())  # Monday


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _series(starts: list[date], counts: Counter, before: int, label) -> list[dict]:
    total = before
    out = []
    for start in starts:
        total += counts.get(start, 0)
        out.append({"start": start.isoformat(), "label": label(start), "count": counts.get(start, 0), "cumulative": total})
    return out


async def registration_growth(session: AsyncSession, now: datetime | None = None) -> dict:
    now_ist = _ist(now or datetime.now(UTC))
    today = now_ist.date()

    rows = (await session.execute(
        select(User.id, User.full_name, User.created_at, User.last_login_at, User.is_email_verified,
               User.is_phone_verified, Tenant.created_at)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(User.deleted_at.is_(None), User.is_superuser.is_(False))
    )).all()
    google = set(await session.scalars(select(OAuthIdentity.user_id)))
    invited = set(await session.scalars(select(Referral.referred_user_id)))
    roles = dict((await session.execute(
        select(ProfessionalProfile.user_id, ProfessionalProfile.professional_role)
    )).all())

    members = []
    for uid, name, created, last_login, email_ok, phone_ok, tenant_created in rows:
        created_ist = _ist(created)
        own_org = abs((_ist(tenant_created) - created_ist).total_seconds()) <= 120
        method = ("google" if uid in google else "whatsapp" if phone_ok else "email") if own_org else "team"
        members.append({
            "id": uid, "name": name, "created": created_ist, "day": created_ist.date(), "method": method,
            "role": roles.get(uid), "verified": bool(email_ok or phone_ok), "invited": uid in invited,
            "returned": bool(last_login and _ist(last_login).date() > created_ist.date()),
        })
    members.sort(key=lambda m: m["created"])

    by_day = Counter(m["day"] for m in members)
    by_week = Counter(_week_start(m["day"]) for m in members)
    by_month = Counter(_month_start(m["day"]) for m in members)

    def between(start: date, end: date) -> int:  # [start, end)
        return sum(n for d, n in by_day.items() if start <= d < end)

    week, month = _week_start(today), _month_start(today)
    tomorrow = today + timedelta(days=1)
    kpis = {
        "today": by_day.get(today, 0), "yesterday": by_day.get(today - timedelta(days=1), 0),
        "this_week": between(week, tomorrow), "last_week_same_point": between(week - timedelta(days=7), today - timedelta(days=6)),
        "last_week": between(week - timedelta(days=7), week),
        "this_month": between(month, tomorrow), "last_month": between(_add_months(month, -1), month),
        "last_7_days": between(today - timedelta(days=6), tomorrow),
        "previous_7_days": between(today - timedelta(days=13), today - timedelta(days=6)),
        "last_30_days": between(today - timedelta(days=29), tomorrow),
        "previous_30_days": between(today - timedelta(days=59), today - timedelta(days=29)),
    }

    day_starts = [today - timedelta(days=i) for i in range(29, -1, -1)]
    week_starts = [week - timedelta(weeks=i) for i in range(11, -1, -1)]
    month_starts = [_add_months(month, -i) for i in range(11, -1, -1)]
    total = len(members)
    best_day, best = (max(by_day.items(), key=lambda kv: (kv[1], kv[0])) if by_day else (None, 0))
    last = members[-1]["created"] if members else None

    def breakdown(counter: Counter, labels: dict) -> list[dict]:
        return [{"key": k or "unknown", "label": labels.get(k, "Not given") if k else "Not given", "count": n}
                for k, n in counter.most_common()]

    return {
        "generated_at": now_ist.isoformat(),
        "total_members": total,
        "self_signups": sum(1 for m in members if m["method"] != "team"),
        "added_by_firms": sum(1 for m in members if m["method"] == "team"),
        "via_invite": sum(1 for m in members if m["invited"]),
        "verified": sum(1 for m in members if m["verified"]),
        "returned": sum(1 for m in members if m["returned"]),
        "kpis": kpis,
        "best_day": {"date": best_day.isoformat(), "count": best} if best_day else None,
        "last_signup_at": last.isoformat() if last else None,
        "days_since_last": (today - last.date()).days if last else None,
        "next_milestone": next((m for m in MILESTONES if m > total), None),
        "previous_milestone": max((m for m in MILESTONES if m <= total), default=0),
        "daily": _series(day_starts, by_day, sum(n for d, n in by_day.items() if d < day_starts[0]),
                         lambda d: d.strftime("%d %b")),
        "weekly": _series(week_starts, by_week, sum(n for d, n in by_week.items() if d < week_starts[0]),
                          lambda d: d.strftime("%d %b")),
        "monthly": _series(month_starts, by_month, sum(n for d, n in by_month.items() if d < month_starts[0]),
                           lambda d: d.strftime("%b %Y")),
        "by_method": breakdown(Counter(m["method"] for m in members), METHOD_LABELS),
        "by_role": breakdown(Counter(m["role"] for m in members), ROLE_LABELS),
        "recent": [
            {"name": m["name"], "joined_at": m["created"].isoformat(), "method": METHOD_LABELS[m["method"]],
             "role": ROLE_LABELS.get(m["role"], "Not given") if m["role"] else "Not given",
             "verified": m["verified"], "invited": m["invited"]}
            for m in reversed(members[-12:])
        ],
    }

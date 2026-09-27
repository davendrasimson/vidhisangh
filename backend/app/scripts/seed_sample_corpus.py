"""Seed realistic **sample** research data (judgments + legal news) for testing
and design — NOT real case law. Every row is marked with a ``sample.vidhisangh``
source URL so it can be cleared and re-seeded without touching real data.

Run:  python -m app.scripts.seed_sample_corpus            # 5000 of each
      python -m app.scripts.seed_sample_corpus --count 2000
      python -m app.scripts.seed_sample_corpus --clear    # remove sample rows

Judgments get a spread of court levels, courts, judges, acts, sections,
keywords, dates and outcomes, plus a set of citation edges so the citation graph
has data. Real bulk ingestion from eSCR/official sources is a separate pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import structlog
from faker import Faker
from sqlalchemy import delete, insert, select

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope
from app.modules.identity.models import User
from app.modules.news.models import NewsCategory, NewsItem
from app.modules.research.models import (
    CaseCitation,
    CitationRelationship,
    CourtLevel,
    Judgment,
)

log = structlog.get_logger("app.seed_sample")
fake = Faker("en_IN")
Faker.seed(42)

SAMPLE_HOST = "https://sample.vidhisangh.local"

HIGH_COURTS = [
    "Delhi High Court", "Bombay High Court", "Calcutta High Court", "Madras High Court",
    "Allahabad High Court", "Karnataka High Court", "Gujarat High Court",
    "Punjab & Haryana High Court", "Kerala High Court", "Telangana High Court",
    "Rajasthan High Court", "Madhya Pradesh High Court", "Patna High Court",
    "Orissa High Court", "Gauhati High Court", "Jharkhand High Court",
]
TRIBUNALS = [
    "National Company Law Tribunal", "National Green Tribunal",
    "Income Tax Appellate Tribunal", "Central Administrative Tribunal",
    "Debts Recovery Tribunal", "Armed Forces Tribunal",
    "Telecom Disputes Settlement and Appellate Tribunal",
    "National Consumer Disputes Redressal Commission",
]
STATES = [
    "Maharashtra", "Delhi", "Karnataka", "Tamil Nadu", "Uttar Pradesh", "Gujarat",
    "West Bengal", "Kerala", "Rajasthan", "Punjab", "Bihar", "Telangana", "Odisha",
]
ACTS = [
    "Indian Penal Code, 1860", "Code of Criminal Procedure, 1973", "Constitution of India",
    "Indian Contract Act, 1872", "Companies Act, 2013", "Income Tax Act, 1961",
    "Code of Civil Procedure, 1908", "Indian Evidence Act, 1872",
    "Arbitration and Conciliation Act, 1996", "Central Goods and Services Tax Act, 2017",
    "Negotiable Instruments Act, 1881", "Transfer of Property Act, 1882",
    "Hindu Marriage Act, 1955", "Insolvency and Bankruptcy Code, 2016",
    "Motor Vehicles Act, 1988", "Consumer Protection Act, 2019",
    "Prevention of Corruption Act, 1988", "SARFAESI Act, 2002",
]
KEYWORDS = [
    "bail", "anticipatory bail", "murder", "culpable homicide", "arbitration award",
    "tax evasion", "fundamental rights", "natural justice", "specific performance",
    "dishonour of cheque", "insolvency", "land acquisition", "maintenance", "custody",
    "service matter", "writ jurisdiction", "quashing of FIR", "compensation",
    "negligence", "contempt", "GST refund", "reservation", "environmental clearance",
    "limitation", "res judicata", "corporate insolvency", "moratorium",
]
OUTCOMES = [
    "Appeal allowed", "Appeal dismissed", "Petition allowed", "Writ petition dismissed",
    "Conviction upheld", "Conviction set aside", "Matter remanded", "SLP dismissed",
    "Bail granted", "Bail rejected", "Arbitral award upheld", "Impugned order set aside",
]
JUDGES = [
    "Chandrachud", "Khanna", "Kaul", "Nagarathna", "Gavai", "Kant", "Bhat", "Narasimha",
    "Roy", "Trivedi", "Bose", "Shah", "Ramana", "Lalit", "Rao", "Joseph", "Oka",
    "Dhulia", "Pardiwala", "Maheshwari", "Reddy", "Banerjee", "Sundresh", "Bhuyan",
]
COMPANIES = [
    "Reliance Infra Pvt. Ltd.", "Tata Steel Ltd.", "Adani Ports Ltd.", "Infosys Ltd.",
    "HDFC Bank Ltd.", "Bharti Airtel Ltd.", "Larsen & Toubro Ltd.", "Vedanta Ltd.",
    "Hindustan Unilever Ltd.", "ITC Ltd.", "Wipro Ltd.", "Mahindra & Mahindra Ltd.",
]


def _party() -> str:
    r = fake.random.random()
    if r < 0.25:
        return f"State of {fake.random.choice(STATES)}"
    if r < 0.40:
        return "Union of India"
    if r < 0.60:
        return fake.random.choice(COMPANIES)
    if r < 0.72:
        return f"Commissioner of Income Tax, {fake.city()}"
    return fake.name()


def _case_name() -> str:
    return f"{_party()} vs {_party()}"


def _judgment_row(i: int, added_by: uuid.UUID) -> dict:
    rnd = fake.random
    level = rnd.choices(
        [CourtLevel.SUPREME_COURT, CourtLevel.HIGH_COURT, CourtLevel.TRIBUNAL,
         CourtLevel.DISTRICT, CourtLevel.OTHER],
        weights=[40, 40, 12, 5, 3],
    )[0]
    year = rnd.randint(2000, 2025)
    jdate = date(year, rnd.randint(1, 12), rnd.randint(1, 28))
    if level == CourtLevel.SUPREME_COURT:
        court = "Supreme Court of India"
        neutral = f"{year} INSC {i + 1}"
        citation = f"({year}) {rnd.randint(1, 15)} SCC {rnd.randint(1, 999)} [S{i + 1}]"
    elif level == CourtLevel.HIGH_COURT:
        court = rnd.choice(HIGH_COURTS)
        neutral = f"{year}:HC:{i + 1}"
        citation = f"({year}) {rnd.randint(1, 6)} {court.split()[0][:3].upper()} {rnd.randint(1, 999)} [H{i + 1}]"
    elif level == CourtLevel.TRIBUNAL:
        court = rnd.choice(TRIBUNALS)
        neutral = None
        citation = f"{year} {court.split()[0][:4].upper()} {rnd.randint(1, 999)} [T{i + 1}]"
    else:
        court = f"District Court, {rnd.choice(STATES)}"
        neutral = None
        citation = f"{year} DC {rnd.randint(1, 9999)} [D{i + 1}]"

    n_judges = rnd.choice([1, 1, 2, 3, 3, 5])
    judges = [f"Justice {rnd.choice(JUDGES)}" for _ in range(n_judges)]
    bench = {1: "Single Judge", 2: "Division Bench", 3: "Three-Judge Bench",
             5: "Constitution Bench"}[n_judges]
    kw = rnd.sample(KEYWORDS, rnd.randint(2, 5))
    acts = rnd.sample(ACTS, rnd.randint(1, 3))
    sections = [f"Section {rnd.randint(1, 500)}" for _ in range(rnd.randint(1, 3))]
    if "Constitution of India" in acts:
        sections.append(f"Article {rnd.randint(12, 395)}")
    return {
        "id": uuid.uuid4(),
        "case_name": _case_name()[:500],
        "citation": citation[:200],
        "neutral_citation": neutral,
        "court": court,
        "court_level": level.value,
        "bench": bench,
        "judges": judges,
        "judgment_date": jdate,
        "acts": acts,
        "sections": sections,
        "keywords": kw,
        "headnote": (
            f"The Court considered questions relating to {kw[0]} under the "
            f"{acts[0]}. {fake.sentence(nb_words=18)} Held: {rnd.choice(OUTCOMES).lower()}."
        ),
        "outcome": rnd.choice(OUTCOMES),
        "url": f"{SAMPLE_HOST}/judgments/{i + 1}",
        "added_by": added_by,
    }


def _news_row(i: int, added_by: uuid.UUID) -> dict:
    rnd = fake.random
    sources = [
        "Supreme Court of India", "Bar & Bench", "LiveLaw", "Press Information Bureau",
        "Reserve Bank of India", "SEBI", "GST Council", "Gazette of India",
        "Ministry of Law & Justice", "Ministry of Corporate Affairs", "CBDT",
        "Competition Commission of India",
    ]
    category = rnd.choice(list(NewsCategory))
    act = rnd.choice(ACTS)
    topic = rnd.choice(KEYWORDS)
    templates = [
        f"Supreme Court clarifies law on {topic}",
        f"Government notifies amendment to the {act}",
        f"{rnd.choice(HIGH_COURTS)} rules on {topic}",
        f"Regulator issues circular on {topic}",
        f"New guidelines released concerning {topic}",
        f"Landmark ruling reshapes {topic} jurisprudence",
    ]
    # published_at is a timezone-naive column → strip tzinfo.
    published = (
        datetime.now(timezone.utc) - timedelta(days=rnd.randint(0, 1460), hours=rnd.randint(0, 23))
    ).replace(tzinfo=None)
    return {
        "id": uuid.uuid4(),
        "title": rnd.choice(templates)[:400],
        "summary": fake.paragraph(nb_sentences=2),
        "source": rnd.choice(sources),
        "category": category.value,
        "url": f"{SAMPLE_HOST}/news/{i + 1}",
        "published_at": published,
        "tags": rnd.sample(KEYWORDS, rnd.randint(1, 4)),
        "added_by": added_by,
    }


async def _clear(session) -> None:
    like = f"{SAMPLE_HOST}%"
    # Citation edges cascade with judgments, but delete explicitly for clarity.
    sample_ids = (
        await session.execute(select(Judgment.id).where(Judgment.url.like(like)))
    ).scalars().all()
    if sample_ids:
        await session.execute(
            delete(CaseCitation).where(CaseCitation.from_judgment_id.in_(sample_ids))
        )
    await session.execute(delete(Judgment).where(Judgment.url.like(like)))
    await session.execute(delete(NewsItem).where(NewsItem.url.like(like)))


async def seed(count: int, clear_only: bool) -> None:
    async with session_scope(bypass_rls=True) as session:
        user_id = (await session.execute(select(User.id).limit(1))).scalar_one()
        await _clear(session)
        if clear_only:
            log.info("sample_cleared")
            return

        # ── Judgments ──────────────────────────────────────────────
        judgments = [_judgment_row(i, user_id) for i in range(count)]
        for start in range(0, len(judgments), 1000):
            await session.execute(insert(Judgment), judgments[start : start + 1000])
        log.info("judgments_seeded", count=len(judgments))

        # ── Citation graph edges (≈0.8 per judgment) ───────────────
        ids = [j["id"] for j in judgments]
        edges = []
        for _ in range(int(count * 0.8)):
            frm, to = fake.random.choice(ids), fake.random.choice(ids)
            if frm == to:
                continue
            edges.append({
                "id": uuid.uuid4(),
                "from_judgment_id": frm,
                "to_judgment_id": to,
                "external_citation": None,
                "relationship_type": fake.random.choice(list(CitationRelationship)).value,
                "added_by": user_id,
            })
        for start in range(0, len(edges), 1000):
            await session.execute(insert(CaseCitation), edges[start : start + 1000])
        log.info("citations_seeded", count=len(edges))

        # ── Legal news ─────────────────────────────────────────────
        news = [_news_row(i, user_id) for i in range(count)]
        for start in range(0, len(news), 1000):
            await session.execute(insert(NewsItem), news[start : start + 1000])
        log.info("news_seeded", count=len(news))


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed sample research/news data.")
    parser.add_argument("--count", type=int, default=5000, help="Rows per section (default 5000).")
    parser.add_argument("--clear", action="store_true", help="Remove sample rows and exit.")
    args = parser.parse_args()
    asyncio.run(seed(args.count, args.clear))


if __name__ == "__main__":  # pragma: no cover
    main()

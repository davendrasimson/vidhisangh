"""eCourts case-lookup seam.

Pulls a case record from the Indian judiciary's eCourts system by **CNR** (the
16-character Case Number Record) or by case type / number / year, and normalises
it into :class:`ECourtsCase` so the matters module never sees a provider's shape.

Follows the pluggable-seam pattern used by storage, payments and oauth: a
provider chosen by ``VS_ECOURTS_PROVIDER``, overridable in tests via
:func:`set_ecourts_client`.

**There is no official public eCourts API.** The National Judicial Data Grid and
the eCourts services portal are built for human use — the case-status pages sit
behind a CAPTCHA, and scraping them is both brittle and a terms-of-service
question. So the default provider is deliberately *unconfigured*: it raises a
clear error rather than pretending, and no scraper ships here. Two honest ways
to make lookups real:

* a licensed commercial feed (several vendors resell eCourts/NJDG data) — write
  an adapter implementing :class:`ECourtsClient`; or
* a registered NJDG/eCourts data-access arrangement, if your firm has one.

``VS_ECOURTS_PROVIDER=sample`` returns a deterministic fabricated record so the
UI and import flow can be exercised without a provider. It is refused in
production, because a fabricated case record on a real matter is worse than no
record at all.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol, runtime_checkable

import structlog
from fastapi import status

from app.core.config import settings
from app.core.exceptions import AppError

log = structlog.get_logger("app.ecourts")

# A CNR is 16 chars: 4-letter establishment code, 6 digits, 4-digit year.
# e.g. DLHC01-000123-2024 is written without separators: DLHC010001232024
CNR_PATTERN = re.compile(r"^[A-Z]{4}[A-Z0-9]{2}\d{6}\d{4}$")


def normalise_cnr(value: str) -> str:
    """Strip separators and upper-case, the form the registries print."""
    return re.sub(r"[\s\-/]", "", (value or "")).upper()


def is_valid_cnr(value: str) -> bool:
    return bool(CNR_PATTERN.match(normalise_cnr(value)))


class ECourtsError(AppError):
    """Lookup could not be completed (upstream problem)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "ecourts_error"
    message = "The eCourts lookup could not be completed."


class ECourtsUnavailable(ECourtsError):
    """No provider is configured — deliberately distinct from "not found"."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "ecourts_unavailable"


class ECourtsNotFound(ECourtsError):
    """The provider answered, but has no such case."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "ecourts_not_found"
    message = "No case matched those details."


@dataclass(slots=True)
class ECourtsParty:
    name: str
    role: str                      # petitioner / respondent / appellant …
    position: int | None = None


@dataclass(slots=True)
class ECourtsAdvocate:
    name: str
    appears_for: str               # the party or side, as the registry prints it
    bar_enrolment_number: str | None = None


@dataclass(slots=True)
class ECourtsHearing:
    date: date
    purpose: str | None = None
    judge: str | None = None


@dataclass(slots=True)
class ECourtsCase:
    """A case as the registry holds it, provider-independent."""

    cnr_number: str
    case_type: str | None = None
    case_number: str | None = None
    case_year: int | None = None
    cause_title: str | None = None

    filing_number: str | None = None
    filing_date: date | None = None
    registration_number: str | None = None
    registration_date: date | None = None

    court_level: str | None = None         # matches matters.CourtLevel values
    court_establishment: str | None = None
    state: str | None = None
    district: str | None = None
    coram: str | None = None

    status: str | None = None              # "Pending" / "Disposed"
    stage: str | None = None
    next_hearing_date: date | None = None
    last_hearing_date: date | None = None
    hearing_purpose: str | None = None
    disposal_date: date | None = None
    disposal_nature: str | None = None

    acts: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    parties: list[ECourtsParty] = field(default_factory=list)
    advocates: list[ECourtsAdvocate] = field(default_factory=list)
    hearings: list[ECourtsHearing] = field(default_factory=list)

    source: str = "unknown"


@runtime_checkable
class ECourtsClient(Protocol):
    async def fetch_by_cnr(self, cnr: str) -> ECourtsCase: ...

    async def search(
        self,
        *,
        case_type: str,
        case_number: str,
        case_year: int,
        state: str | None = None,
        district: str | None = None,
        court_establishment: str | None = None,
    ) -> list[ECourtsCase]: ...


class UnconfiguredECourtsClient:
    """Default. Refuses clearly instead of guessing."""

    _MESSAGE = (
        "eCourts lookup is not configured. There is no official public eCourts "
        "API; connect a licensed case-data provider by implementing ECourtsClient "
        "and setting VS_ECOURTS_PROVIDER, or enter the case details manually."
    )

    async def fetch_by_cnr(self, cnr: str) -> ECourtsCase:
        raise ECourtsUnavailable(self._MESSAGE)

    async def search(self, **_: object) -> list[ECourtsCase]:
        raise ECourtsUnavailable(self._MESSAGE)


class SampleECourtsClient:
    """Deterministic fabricated records, for local development only.

    Seeded from the CNR so the same input always yields the same case — which
    makes the import flow demoable and testable. Never enabled in production.
    """

    _COURTS = [
        ("high_court", "Delhi High Court", "Delhi", "New Delhi"),
        ("district", "Saket District Court", "Delhi", "South Delhi"),
        ("high_court", "Bombay High Court", "Maharashtra", "Mumbai"),
        ("tribunal", "NCLT, Mumbai Bench", "Maharashtra", "Mumbai"),
    ]
    _TYPES = ["W.P.(C)", "CRL.A.", "C.S.(OS)", "CIVIL APPEAL", "O.A."]
    _PURPOSES = ["For hearing", "For final arguments", "For filing reply", "For orders"]
    _ACTS = [
        ("Code of Civil Procedure, 1908", ["Order VII Rule 11", "Section 151"]),
        ("Indian Penal Code, 1860", ["Section 420", "Section 120B"]),
        ("Arbitration and Conciliation Act, 1996", ["Section 34", "Section 37"]),
        ("Constitution of India", ["Article 226", "Article 14"]),
    ]

    def _seed(self, key: str) -> int:
        return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)

    def _build(self, cnr: str, case_type: str | None = None,
               case_number: str | None = None, case_year: int | None = None) -> ECourtsCase:
        n = self._seed(cnr)
        level, establishment, state, district = self._COURTS[n % len(self._COURTS)]
        ctype = case_type or self._TYPES[n % len(self._TYPES)]
        cnum = case_number or str(1000 + (n % 9000))
        cyear = case_year or (2019 + (n % 7))
        act, sections = self._ACTS[n % len(self._ACTS)]
        filed = date(cyear, 1 + (n % 12), 1 + (n % 27))
        today = date.today()

        return ECourtsCase(
            cnr_number=normalise_cnr(cnr),
            case_type=ctype,
            case_number=cnum,
            case_year=cyear,
            cause_title=f"Sample Petitioner {n % 97} vs Sample Respondent {n % 53}",
            filing_number=f"F/{cnum}/{cyear}",
            filing_date=filed,
            registration_number=f"{ctype} {cnum}/{cyear}",
            registration_date=filed + timedelta(days=14),
            court_level=level,
            court_establishment=establishment,
            state=state,
            district=district,
            coram=f"Hon'ble Justice Sample {n % 31}",
            status="Pending",
            stage="Arguments" if n % 2 else "Pleadings",
            next_hearing_date=today + timedelta(days=7 + (n % 45)),
            last_hearing_date=today - timedelta(days=10 + (n % 30)),
            hearing_purpose=self._PURPOSES[n % len(self._PURPOSES)],
            acts=[act],
            sections=sections,
            parties=[
                ECourtsParty(name=f"Sample Petitioner {n % 97}", role="petitioner", position=1),
                ECourtsParty(name=f"Sample Respondent {n % 53}", role="respondent", position=1),
            ],
            advocates=[
                ECourtsAdvocate(name=f"Adv. A. Sample {n % 19}", appears_for="petitioner"),
                ECourtsAdvocate(name=f"Adv. B. Counsel {n % 23}", appears_for="respondent"),
            ],
            hearings=[
                ECourtsHearing(
                    date=today - timedelta(days=10 + (n % 30)),
                    purpose="For hearing",
                    judge=f"Hon'ble Justice Sample {n % 31}",
                )
            ],
            source="sample",
        )

    async def fetch_by_cnr(self, cnr: str) -> ECourtsCase:
        cnr = normalise_cnr(cnr)
        if not is_valid_cnr(cnr):
            raise ECourtsNotFound(f"'{cnr}' is not a valid 16-character CNR.")
        return self._build(cnr)

    async def search(
        self,
        *,
        case_type: str,
        case_number: str,
        case_year: int,
        state: str | None = None,
        district: str | None = None,
        court_establishment: str | None = None,
    ) -> list[ECourtsCase]:
        key = f"{case_type}{case_number}{case_year}{state or ''}{district or ''}"
        digest = hashlib.sha256(key.encode()).hexdigest().upper()
        synthetic_cnr = f"SMPL01{digest[:6].translate(str.maketrans('ABCDEF', '012345'))}{case_year}"
        return [self._build(synthetic_cnr, case_type, case_number, case_year)]


_client: ECourtsClient | None = None


def get_ecourts_client() -> ECourtsClient:
    """The provider selected by ``VS_ECOURTS_PROVIDER`` (default: unconfigured)."""
    global _client
    if _client is None:
        provider = os.environ.get("VS_ECOURTS_PROVIDER", "").strip().lower()
        if provider == "sample" and not settings.is_production:
            log.warning("ecourts_sample_provider_enabled")
            _client = SampleECourtsClient()
        else:
            if provider == "sample":
                log.error("ecourts_sample_provider_refused_in_production")
            _client = UnconfiguredECourtsClient()
    return _client


def set_ecourts_client(client: ECourtsClient | None) -> None:
    """Swap the provider (tests, or a real adapter once you have a feed)."""
    global _client
    _client = client

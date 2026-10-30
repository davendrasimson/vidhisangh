"""Statutory references in a draft: old criminal law → new, from the BPRD tables.

The cite check also reads every "Section 420 IPC", "u/s 438 Cr.P.C.",
"Section 65B of the Evidence Act" (and the BNS / BNSS / BSA equivalents) in a
draft and says what each is under the Bharatiya Nyaya Sanhita, the Bharatiya
Nagarik Suraksha Sanhita and the Bharatiya Sakshya Adhiniyam — or that the
old section was not carried over (IPC 124A, 377, 497 …). The tables are the
BPRD correspondence tables already used by the public converter pages; the
copies in ``correspondence/`` are kept identical to
``frontend/content/correspondence/`` (a test checks).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.modules.research.normalise import _ACT_NAME, _canonical_act

# Like normalise._SECTION_RE but only for sections (no Articles/Rules) and
# tolerant of lettered sub-clauses — "376(2)(n)", "304B", "65B".
_SUB = r"(?:\s*\(\s*[0-9A-Za-z]{1,3}\s*\))*"
_SECTION_RE = re.compile(
    r"\b(?P<kind>Sections?|Sec\.?|Ss?\.|u/s\.?|under\s+s(?:ection)?\.?)\s*"
    rf"(?P<nums>\d{{1,4}}[A-Z]{{0,2}}{_SUB}(?:\s*(?:,|and|&|/|to|read\s+with|r/w)\s*\d{{1,4}}[A-Z]{{0,2}}{_SUB})*)"
    r"\s*(?:of\s+(?:the\s+)?)?"
    r"(?P<act>" + _ACT_NAME + r"|[A-Z][A-Za-z.]{1,10}\.?(?:\s?Act)?)?",
    re.M,
)

_DIR = Path(__file__).with_name("correspondence")
# Canonical act name (normalise._ACT_ALIASES) → table key; the old Acts and the new ones.
_ACT_KEYS = (
    ("Penal Code", "ipc"), ("Criminal Procedure", "crpc"), ("Evidence Act", "evidence"),
    ("Nyaya Sanhita", "bns"), ("Nagarik Suraksha", "bnss"), ("Sakshya", "bsa"),
)
NEW_FOR_OLD = {"ipc": "bns", "crpc": "bnss", "evidence": "bsa"}
OLD_FOR_NEW = {v: k for k, v in NEW_FOR_OLD.items()}
SHORT = {"ipc": "IPC", "crpc": "CrPC", "evidence": "Evidence Act", "bns": "BNS", "bnss": "BNSS", "bsa": "BSA"}
# Last section of each Act, to tell a mistyped number from an omitted section.
LAST_SECTION = {"ipc": 511, "crpc": 484, "evidence": 167, "bns": 358, "bnss": 531, "bsa": 170}
CONVERTER_PATH = {"ipc": "ipc-to-bns", "crpc": "crpc-to-bnss", "evidence": "evidence-to-bsa"}


@dataclass(frozen=True)
class Table:
    old_to_new: dict[str, list[tuple[str, str]]]   # old section → [(new section, subject)]
    new_subject: dict[str, str]                     # new section → subject
    new_to_old: dict[str, list[str]]                # new section → old sections


@lru_cache(maxsize=1)
def tables() -> dict[str, Table]:
    """The three correspondence tables keyed by the new Act (bns / bnss / bsa)."""
    out: dict[str, Table] = {}
    for new_act in ("bns", "bnss", "bsa"):
        data = json.loads((_DIR / f"{new_act}.json").read_text(encoding="utf-8"))
        old_to_new: dict[str, list[tuple[str, str]]] = {}
        new_subject: dict[str, str] = {}
        new_to_old: dict[str, list[str]] = {}
        for e in data["entries"]:
            new_subject[e["new"]] = e["subject"]
            new_to_old[e["new"]] = list(e["old"])
            for old in e["old"]:
                old_to_new.setdefault(old, []).append((e["new"], e["subject"]))
        out[new_act] = Table(old_to_new, new_subject, new_to_old)
    return out


def act_key(canonical: str | None) -> str | None:
    if not canonical:
        return None
    for needle, key in _ACT_KEYS:
        if needle in canonical:
            return key
    return None


@dataclass
class StatuteFinding:
    act: str                         # ipc | crpc | evidence | bns | bnss | bsa
    act_label: str
    section: str                     # as cited, e.g. "376(2)(n)"
    base: str                        # the section number the tables key by, e.g. "376"
    occurrences: int
    contexts: list[str]
    status: str                      # mapped | not_carried | new_law | unknown
    new_act: str | None = None
    new_act_label: str | None = None
    new_sections: list[str] = field(default_factory=list)
    subject: str | None = None
    old_sections: list[str] = field(default_factory=list)   # for a new-law reference: what it replaced
    converter_path: str | None = None                       # public page for the old section
    note: str | None = None


_CONTEXT = 80
_BASE_RE = re.compile(r"^(\d{1,4}[A-Z]{0,2})")


def _base(section: str) -> str:
    m = _BASE_RE.match(section)
    return m.group(1) if m else section


def find_statute_references(text: str) -> list[StatuteFinding]:
    """Every IPC / CrPC / Evidence Act / BNS / BNSS / BSA section cited in the text, grouped."""
    found: dict[tuple[str, str], StatuteFinding] = {}
    for m in _SECTION_RE.finditer(text):
        key = act_key(_canonical_act(m.group("act")))
        if key is None or not m.group("kind").lower().startswith(("section", "sec", "s.", "ss", "u/s", "under")):
            continue
        ctx = re.sub(r"\s+", " ", text[max(0, m.start() - _CONTEXT): m.end() + _CONTEXT]).strip()
        for num in re.split(r"\s*(?:,|and|&|/|to|read\s+with|r/w)\s*", m.group("nums")):
            num = re.sub(r"\s+", "", num)
            if not num:
                continue
            base = _base(num)
            k = (key, base)
            if k in found:
                found[k].occurrences += 1
                if len(found[k].contexts) < 3 and ctx not in found[k].contexts:
                    found[k].contexts.append(ctx)
                continue
            found[k] = _classify(key, num, base, ctx)
    return list(found.values())


def _classify(key: str, section: str, base: str, ctx: str) -> StatuteFinding:
    f = StatuteFinding(act=key, act_label=SHORT[key], section=section, base=base, occurrences=1, contexts=[ctx], status="unknown")
    number = int(re.match(r"\d+", base).group()) if re.match(r"\d+", base) else 0
    if key in NEW_FOR_OLD:
        new_act = NEW_FOR_OLD[key]
        f.new_act, f.new_act_label = new_act, SHORT[new_act]
        f.converter_path = f"/acts/{CONVERTER_PATH[key]}/section-{base.lower()}/"
        hits = tables()[new_act].old_to_new.get(base, [])
        if hits:
            f.status = "mapped"
            f.new_sections = [n for n, _ in hits]
            f.subject = hits[0][1]
            f.note = f"For acts and proceedings governed by the new law (from 1 July 2024) cite {SHORT[new_act]} {', '.join(f.new_sections)}."
        elif 1 <= number <= LAST_SECTION[key]:
            f.status = "not_carried"
            f.note = f"{SHORT[key]} {base} has no corresponding provision in the {SHORT[new_act]} (omitted or struck down); check before relying on it for a post-1 July 2024 matter."
        else:
            f.note = f"The {SHORT[key]} has no Section {base}; check the number."
    else:
        table = tables()[key]
        exact = section if section in table.new_subject else base
        if exact in table.new_subject:
            f.status = "new_law"
            f.subject = table.new_subject[exact]
            f.old_sections = table.new_to_old.get(exact, [])
            old_act = OLD_FOR_NEW[key]
            f.note = (f"Replaces {SHORT[old_act]} {', '.join(f.old_sections)}." if f.old_sections
                      else f"New provision with no {SHORT[old_act]} equivalent.")
        elif 1 <= number <= LAST_SECTION[key]:
            f.status = "new_law"
            f.note = "Section exists; its sub-section is not listed separately in the correspondence table."
        else:
            f.note = f"The {SHORT[key]} has no Section {base}; check the number."
    return f

"""Rule-based enrichment of judgment text (no network, no PDF)."""

from __future__ import annotations

from app.core.judgment_enrichment import (
    Enrichment,
    RuleBasedEnricher,
    get_judgment_enricher,
    set_judgment_enricher,
)

# Shaped like a modern Supreme Court Report: coram line, editorial headnote
# (with its "prepared by" credit), the index blocks, then the judgment body.
MODERN_REPORT = """
[2025] 1 S.C.R. 105 : 2025 INSC 20
Urmila Dixit
v.
Sunil Sharan Dixit and Ors.
02 January 2025
[C.T. Ravikumar and Sanjay Karol,* JJ.]

Headnotes†
Maintenance and Welfare of the Parents and Senior Citizens Act, 2007 - s.23 -
Held: Yes - the Gift Deed is liable to be quashed. [Paras 21, 23, 26]

List of Acts
Maintenance and Welfare of the Parents and Senior Citizens Act, 2007.

List of Keywords
Transfer of property; Gift Deed; Maintenance of senior citizens.

Case Arising From
CIVIL APPELLATE JURISDICTION: Civil Appeal No. 10927 of 2024

25. The Tribunal was within its jurisdiction to order restoration of possession,
Section 23 being a standalone provision of the Act, and the relief available to
senior citizens is intrinsically linked to the objects of the Act as set out in
Article 21 of the Constitution of India.
26. In view of the above, the impugned judgment and order is set aside.
Consequently, the Gift Deed dated 07.09.2019 is quashed. In the attending facts
and circumstances of this case, the Appeal is allowed. Possession of the premises
shall be restored to the Appellant by 28.02.2025.
27. Pending applications, if any, shall stand disposed of.
Result of the case: Appeal allowed.
†Headnotes prepared by: Divya Pandey
"""

# Older reports carry no index blocks and print gutter letters (A-H).
LEGACY_REPORT = """
[2011] 2 S.C.R. 919
[R.V. Raveendran and A.K. Patnaik, JJ.]

CIVIL APPELLATE JURISDICTION
12. The appellant was convicted under Section 302 of the Indian Penal Code, 1860
and the High Court declined to interfere, which in our view was C erroneous
having regard to Article 14 of the Constitution of India.
13. As a result, the appeal is allowed and the order of the High Court is set
aside and the writ petition filed by the first D respondent is dismissed.
R.P. Appeal allowed.
"""


def test_modern_report_uses_its_own_index_blocks() -> None:
    found = RuleBasedEnricher().enrich(MODERN_REPORT)
    assert "Maintenance and Welfare of the Parents and Senior Citizens Act, 2007" in found.acts
    # The Constitution is cited in the body, so it is picked up alongside the index.
    assert "Constitution of India" in found.acts
    assert "Gift Deed" in found.keywords
    assert "Section 23" in found.sections
    assert "Article 21" in found.sections


def test_bench_comes_from_the_coram_not_the_author() -> None:
    found = RuleBasedEnricher().enrich(MODERN_REPORT)
    assert found.bench == "Division Bench"
    assert found.judges == ["Justice C.T. Ravikumar", "Justice Sanjay Karol"]


def test_headnote_is_the_courts_disposal_not_the_editorial_headnote() -> None:
    """The SCR headnote is a named editor's work (EBC v. Modak) — never copied."""
    found = RuleBasedEnricher().enrich(MODERN_REPORT)
    assert found.headnote is not None
    assert "the Appeal is allowed" in found.headnote
    # Nothing from the editorial block or its credit line.
    assert "Held: Yes" not in found.headnote
    assert "Divya Pandey" not in found.headnote
    assert "Headnotes prepared by" not in found.headnote
    assert "Result of the case" not in found.headnote


def test_legacy_report_falls_back_to_pattern_matching() -> None:
    found = RuleBasedEnricher().enrich(LEGACY_REPORT)
    assert "Indian Penal Code, 1860" in found.acts
    assert "Constitution of India" in found.acts
    assert "Section 302" in found.sections
    assert found.bench == "Division Bench"
    assert found.keywords, "topic vocabulary should fire when there is no index block"


def test_legacy_headnote_drops_gutter_letters_and_result_stamp() -> None:
    found = RuleBasedEnricher().enrich(LEGACY_REPORT)
    assert found.headnote is not None
    assert "the appeal is allowed" in found.headnote
    assert "first respondent is dismissed" in found.headnote  # the stray "D" is gone
    assert not found.headnote.rstrip().endswith("Appeal allowed.")


def test_empty_text_yields_nothing() -> None:
    found = RuleBasedEnricher().enrich("   ")
    assert found.is_empty()


def test_enricher_is_swappable() -> None:
    class Stub:
        def enrich(self, text: str) -> Enrichment:
            return Enrichment(keywords=["stub"])

    try:
        set_judgment_enricher(Stub())
        assert get_judgment_enricher().enrich("anything").keywords == ["stub"]
    finally:
        set_judgment_enricher(None)
    assert isinstance(get_judgment_enricher(), RuleBasedEnricher)

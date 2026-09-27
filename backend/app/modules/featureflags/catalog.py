"""The canonical catalog of feature flags.

Adding a flag here makes it appear in the admin UI and resolvable via the API
with its platform default; a tenant may then override it. Keep keys stable —
they are the contract the app and frontend gate on.
"""

from __future__ import annotations

from typing import NamedTuple


class FlagDef(NamedTuple):
    key: str
    name: str
    description: str
    default: bool


FLAG_CATALOG: list[FlagDef] = [
    FlagDef("client_portal", "Client portal", "Magic-link portal for clients to track their matters.", True),
    FlagDef("legal_news", "Legal news feed", "Curated legal news inside the app.", True),
    FlagDef("marketplace", "Marketplace", "Cross-firm referrals, local counsel & expert listings.", True),
    FlagDef("analytics", "Analytics dashboards", "Revenue, caseload, pipeline & productivity insights.", True),
    # Flags are enforced server-side (`require_flag`) since the 2026-09 audit
    # (A-32); online_payments defaults on so the existing payments flow keeps
    # working — turn it off per tenant to close the payments API entirely.
    FlagDef("online_payments", "Online payments", "Collect invoice payments online via Razorpay.", True),
    FlagDef("ai_drafting", "AI drafting", "Draft documents with AI (requires LLM infrastructure).", False),
    FlagDef("semantic_search", "Semantic research", "Vector/semantic search over the corpus (requires vector DB).", False),
]

CATALOG_BY_KEY: dict[str, FlagDef] = {f.key: f for f in FLAG_CATALOG}
FLAG_KEYS: set[str] = set(CATALOG_BY_KEY)

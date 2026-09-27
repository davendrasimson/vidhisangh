"""Legal news feed (Phase 4).

A **global, cross-tenant** feed of legal-sector news — SC/HC/tribunal rulings,
gazette notifications, RBI/SEBI/GST circulars, etc. — with source/category
filters and keyword search. Like the research corpus, this is shared reference
data (no tenant scoping). AI digests over the feed are a deferred follow-up that
needs the LLM infrastructure; this module is the infra-independent data layer.
"""

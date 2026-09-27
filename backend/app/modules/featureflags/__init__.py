"""Feature flags (Phase 6 — Administration).

Per-tenant capability toggles. A code-defined catalog lists every known flag
with its platform default; tenants persist overrides in ``feature_flags``
(tenant-scoped + RLS). The resolved view (catalog merged with overrides) lets
the app and the frontend gate capabilities per tenant.
"""

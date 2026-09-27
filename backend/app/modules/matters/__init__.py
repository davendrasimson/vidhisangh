"""Matter / case management (Phase 3 — practice management).

Unlike the cross-tenant social layer, matters are **tenant-private**: a firm's
cases, parties, hearings, tasks and notes never leave the firm. All tables are
``TenantScopedBase`` and protected by PostgreSQL row-level security (see the
migration), so isolation is enforced at the database, not just the app.
"""

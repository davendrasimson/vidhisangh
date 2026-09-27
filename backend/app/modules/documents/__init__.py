"""Document management (Phase 3 — practice management).

Tenant-private documents with folders, versioning and check-in/check-out. Bytes
live in pluggable object storage (see ``app.core.storage``); the database holds
metadata + version history. All tables are ``TenantScopedBase`` with row-level
security. OCR, preview rendering, diff comparison and Elasticsearch full-text
search are documented follow-ups (they need dedicated infrastructure).
"""

"""API keys / service accounts (Phase 6 — Integrations).

Long-lived, tenant-scoped bearer tokens for programmatic access. A key carries an
explicit set of permission scopes (a subset of its creator's) and authenticates
as its creator with only those scopes — least-privilege for machine callers.
Only the SHA-256 hash of a key is stored; the plaintext is shown once at creation.
"""

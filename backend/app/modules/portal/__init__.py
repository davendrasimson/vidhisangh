"""Client portal (Phase 3 — practice management).

Gives a firm's clients a secure, login-free window into their matter: progress,
firm updates, approval requests and shared documents. Access is by an
unguessable per-matter **token** (magic-link style) rather than a full external
user account, so clients need no credentials. Firm-side management is JWT + RBAC
(``client:*``); the client-facing endpoints authenticate by token. All tables
are tenant-scoped with row-level security.
"""

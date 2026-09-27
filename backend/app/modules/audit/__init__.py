"""Audit trail (Phase 6 — Administration / Security).

An append-only record of significant actions within a tenant. Services record
events via :func:`service.record_audit`; the admin log viewer reads them. Rows
are tenant-scoped with RLS and never updated after creation.
"""

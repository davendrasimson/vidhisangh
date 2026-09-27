"""In-app notifications (Phase 2 hardening).

A **global, cross-tenant** leaf module: social events (mentions, connection
requests, group invites, endorsements…) originate across firms, so notifications
are keyed by recipient ``user_id`` with a denormalised actor snapshot. Other
modules record events via :func:`service.create_notification`; this module never
imports them, avoiding circular dependencies.
"""

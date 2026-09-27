"""Subscription plans (Phase 6 — Administration).

A code-defined catalog describes each :class:`PlanTier` (price, limits,
features). The tenant's current tier lives on the ``tenants`` row (``plan`` +
``status``) — no separate table — and this module resolves it against the
catalog and reports live usage against the plan's limits.

Collecting payment for a paid plan (via Razorpay) is the go-live step and is
parked with the other deferred-infra items; changing plan here updates the
subscription record immediately.
"""

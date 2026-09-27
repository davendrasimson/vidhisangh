"""Outbound webhooks (Phase 6 — Integrations).

Tenants register endpoint URLs subscribed to platform event types; when an event
fires, :func:`service.emit_event` POSTs a signed JSON payload to each subscribed
endpoint and records the outcome in a delivery log. Signing uses HMAC-SHA256 over
the raw body (the same scheme as the Razorpay webhook verification), so receivers
can authenticate deliveries.
"""

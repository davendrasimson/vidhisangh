"""Payments (Phase 5) — online payments via the Razorpay gateway.

Tenant-scoped payment records backing the checkout flow: create an order, open
Razorpay Checkout on the client, verify the returned signature, and reconcile via
webhook. The gateway itself is abstracted in ``app.core.payments`` (mock when no
keys are configured, live Razorpay when they are), so this module is testable
without live credentials.
"""

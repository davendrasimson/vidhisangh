"""Billing (Phase 5) — invoices, line items, GST and online collection.

Tenant-private invoicing: draft invoices with line items, GST/tax, and a pay
flow that reuses the ``payments`` module (Razorpay). On successful payment the
invoice is reconciled (amount paid + status). Time tracking, retainers, trust
accounting and recurring invoices are follow-ups. All tables are
``TenantScopedBase`` with RLS.
"""

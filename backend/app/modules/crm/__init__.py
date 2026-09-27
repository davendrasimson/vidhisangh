"""CRM (Phase 5) — leads, pipeline, consultations & follow-ups.

Tenant-private client-development data: leads flow through a pipeline (new →
contacted → qualified → consultation → won/lost), carry activities (calls,
emails, meetings, follow-ups), and can be **converted into a matter**. Source
analytics summarise where leads come from and how they convert. Marketing
campaigns are a follow-up. All tables are ``TenantScopedBase`` with RLS.
"""

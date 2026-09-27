"""Direct & group messaging (Phase 2).

A **global, cross-tenant** layer like the professional network — advocates from
different firms message each other. Conversations are either 1:1 (``direct``,
deduplicated via a canonical ``direct_key``) or ``group`` chats. Participant and
sender display fields are denormalised snapshots so threads render without
cross-tenant identity joins. Unread state is tracked per participant via
``last_read_at``. Real-time delivery (WebSocket) and presence are a follow-up;
this layer is REST + read-tracking.
"""

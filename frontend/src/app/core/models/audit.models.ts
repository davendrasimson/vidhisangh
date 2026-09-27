/** Audit-trail contracts (mirrors the backend audit module). */

export interface AuditEvent {
  id: string;
  actor_id: string | null;
  actor_label: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  summary: string;
  meta: Record<string, unknown> | null;
  created_at: string;
}

/** Webhook contracts (mirrors the backend webhooks module). */

export interface EventType {
  key: string;
  description: string;
}

export interface Webhook {
  id: string;
  url: string;
  description: string | null;
  event_types: string[];
  is_active: boolean;
  created_at: string;
}

export interface WebhookCreated extends Webhook {
  secret: string; // returned once on creation
}

export interface WebhookDelivery {
  id: string;
  endpoint_id: string;
  event_type: string;
  status: string; // "success" | "failed"
  status_code: number | null;
  detail: string | null;
  created_at: string;
}

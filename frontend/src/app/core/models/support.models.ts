export type TicketStatus = 'open' | 'in_progress' | 'waiting_on_user' | 'on_hold' | 'closed' | 'reopened';
export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent';

export interface TicketMessage { id: string; author_id: string; author_name: string; is_staff: boolean; body: string; created_at: string; }
export interface SupportTicket {
  id: string; tenant_id: string; ticket_number: string; requester_id: string; requester_name: string;
  requester_email: string; subject: string; description: string; category: string; priority: TicketPriority;
  status: TicketStatus; page_url: string | null; assigned_to_id: string | null; assigned_to_name: string | null;
  first_response_at: string | null; closed_at: string | null; created_at: string; updated_at: string;
  messages: TicketMessage[];
}
export interface PlatformOverview { users_total: number; users_active: number; users_blocked: number; users_new_30d: number; tenants_total: number; tenants_active: number; tenants_suspended: number; posts_total: number; posts_removed: number; tickets_open: number; tickets_urgent: number; tickets_overdue: number; tickets_closed: number; }
export interface PlatformUser { id: string; tenant_id: string; tenant_name: string; full_name: string; email: string; is_active: boolean; is_superuser: boolean; is_email_verified: boolean; mfa_enabled: boolean; last_login_at: string | null; created_at: string; post_count: number; ticket_count: number; connection_count?: number; comment_count?: number; last_ticket_at?: string | null; }
export interface PlatformTenant { id: string; name: string; slug: string; status: string; plan: string; type: string; created_at: string; user_count: number; active_user_count: number; matter_count: number; invoice_count: number; ticket_count: number; }
export interface PlatformPost { id: string; author_id: string; author_name: string; title: string | null; content: string; visibility: string; like_count: number; comment_count: number; created_at: string; deleted_at: string | null; }
export interface AdminAction { id: string; actor_email: string; action: string; entity_type: string; entity_id: string; reason: string | null; detail: Record<string, unknown> | null; created_at: string; }

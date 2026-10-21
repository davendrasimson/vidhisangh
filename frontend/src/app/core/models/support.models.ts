export type TicketStatus = 'open' | 'in_progress' | 'waiting_on_user' | 'on_hold' | 'closed' | 'reopened';
export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent';

export interface TicketMessage { id: string; author_id: string; author_name: string; is_staff: boolean; body: string; created_at: string; }
export interface SupportTicket {
  id: string; tenant_id: string; ticket_number: string; requester_id: string; requester_name: string;
  requester_email: string; subject: string; description: string; category: string; priority: TicketPriority;
  status: TicketStatus; page_url: string | null; assigned_to_id: string | null; assigned_to_name: string | null;
  reported_post_id: string | null; reported_user_id: string | null; report_context: { author_name?: string; title?: string; content?: string; visibility?: string; created_at?: string; report_category?: string } | null;
  first_response_at: string | null; closed_at: string | null; created_at: string; updated_at: string;
  messages: TicketMessage[];
}
export interface PlatformOverview { users_total: number; users_active: number; users_blocked: number; users_new_30d: number; tenants_total: number; tenants_active: number; tenants_suspended: number; posts_total: number; posts_removed: number; tickets_open: number; tickets_urgent: number; tickets_overdue: number; tickets_closed: number; }
export interface PlatformUser { id: string; tenant_id: string; tenant_name: string; full_name: string; email: string; is_active: boolean; is_superuser: boolean; is_email_verified: boolean; mfa_enabled: boolean; last_login_at: string | null; posting_restricted_until: string | null; network_profile_removed_at: string | null; created_at: string; post_count: number; ticket_count: number; connection_count?: number; comment_count?: number; last_ticket_at?: string | null; }
export interface PlatformTenant { id: string; name: string; slug: string; status: string; plan: string; type: string; created_at: string; user_count: number; active_user_count: number; matter_count: number; invoice_count: number; ticket_count: number; }
export interface PlatformPost { id: string; author_id: string; author_name: string; title: string | null; content: string; visibility: string; like_count: number; comment_count: number; created_at: string; deleted_at: string | null; }
export interface AdminAction { id: string; actor_email: string; action: string; entity_type: string; entity_id: string; reason: string | null; detail: Record<string, unknown> | null; created_at: string; }

export interface GrowthPoint { start: string; label: string; count: number; cumulative: number; }
export interface GrowthSlice { key: string; label: string; count: number; }
export interface GrowthRecent { name: string; joined_at: string; method: string; role: string; verified: boolean; invited: boolean; }
export interface RegistrationGrowth {
  generated_at: string; total_members: number; self_signups: number; added_by_firms: number; via_invite: number;
  verified: number; returned: number;
  kpis: { today: number; yesterday: number; this_week: number; last_week_same_point: number; last_week: number;
    this_month: number; last_month: number; last_7_days: number; previous_7_days: number; last_30_days: number; previous_30_days: number; };
  best_day: { date: string; count: number } | null; last_signup_at: string | null; days_since_last: number | null;
  next_milestone: number | null; previous_milestone: number;
  daily: GrowthPoint[]; weekly: GrowthPoint[]; monthly: GrowthPoint[];
  by_method: GrowthSlice[]; by_role: GrowthSlice[]; recent: GrowthRecent[];
  /** Anonymous daily step counters (sign-up funnel), last 7 / 30 days. */
  funnel?: { last_7_days: GrowthFunnelStep[]; last_30_days: GrowthFunnelStep[]; since: string | null };
}

export interface GrowthFunnelStep { step: string; count: number; }

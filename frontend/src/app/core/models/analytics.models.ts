/** Analytics API contracts (mirrors the backend analytics module). */

export interface Bucket {
  key: string;
  count: number;
  amount: number;
}

export interface RevenueSummary {
  total_invoiced: number;
  total_collected: number;
  outstanding: number;
  overdue_amount: number;
  invoice_count: number;
  by_status: Bucket[];
}

export interface MattersSummary {
  total: number;
  open: number;
  by_status: Bucket[];
  by_type: Bucket[];
  by_stage: Bucket[];
}

export interface PipelineSummary {
  total_leads: number;
  open_value: number;
  won_value: number;
  won_count: number;
  lost_count: number;
  conversion_rate: number; // 0..1
  by_status: Bucket[];
}

export interface ProductivitySummary {
  open_tasks: number;
  overdue_tasks: number;
  upcoming_hearings: number;
  hearings_next_7d: number;
}

export interface OperationsSummary {
  submitted_time_entries: number;
  unbilled_time_entries: number;
  unbilled_time_hours: number;
  unbilled_time_value: number;
  pending_signatures: number;
  matter_documents: number;
  follow_ups_due: number;
}

export interface TrendPoint {
  month: string; // "YYYY-MM"
  invoiced: number;
  collected: number;
}

export interface AnalyticsOverview {
  revenue: RevenueSummary;
  matters: MattersSummary;
  pipeline: PipelineSummary;
  productivity: ProductivitySummary;
  operations: OperationsSummary;
  revenue_trend: TrendPoint[];
}

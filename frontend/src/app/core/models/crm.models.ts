/** CRM API contracts (mirrors the backend crm module). */

export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'consultation' | 'won' | 'lost';
export type LeadSource = 'referral' | 'website' | 'walk_in' | 'call' | 'social' | 'other';
export type ActivityType = 'note' | 'call' | 'email' | 'meeting' | 'consultation';

export interface Lead {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  source: LeadSource;
  status: LeadStatus;
  practice_area: string | null;
  notes: string | null;
  estimated_value: string | number | null;
  referred_by: string | null;
  assigned_to: string | null;
  converted_matter_id: string | null;
  client_id: string | null;
  created_at: string;
}

export interface LeadActivity {
  id: string;
  lead_id: string;
  type: ActivityType;
  subject: string | null;
  body: string | null;
  due_on: string | null;
  completed: boolean;
  completed_at: string | null;
  created_at: string;
}

export interface LeadDetail extends Lead {
  activities: LeadActivity[];
}

export interface LeadCreate {
  name: string;
  email?: string | null;
  phone?: string | null;
  source?: LeadSource;
  practice_area?: string | null;
  estimated_value?: number | null;
  referred_by?: string | null;
}

export interface PipelineColumn {
  status: LeadStatus;
  count: number;
  value: string | number;
  leads: Lead[];
}

export interface SourceStat {
  source: LeadSource;
  total: number;
  won: number;
}

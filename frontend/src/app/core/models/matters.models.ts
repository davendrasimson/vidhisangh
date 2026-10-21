/** Matters (case management) API contracts (mirrors the backend matters module). */

export type MatterType = 'litigation' | 'advisory' | 'arbitration' | 'corporate' | 'other';
export type MatterStatus = 'open' | 'on_hold' | 'closed';
export type MatterStage =
  | 'intake' | 'filing' | 'pleadings' | 'evidence' | 'arguments' | 'judgment' | 'closed';
export type Priority = 'low' | 'medium' | 'high';
export type HearingStatus = 'scheduled' | 'held' | 'adjourned' | 'cancelled';
export type TaskStatus = 'open' | 'done';

export type MatterCustomFieldType =
  | 'text' | 'multiline' | 'rich_text' | 'number' | 'amount'
  | 'dropdown' | 'multi_select' | 'date' | 'boolean' | 'email' | 'phone' | 'url';

export interface MatterCustomSection {
  id: string;
  name: string;
  description: string | null;
  position: number;
}

export interface MatterCustomField {
  id: string;
  section_key: string;
  custom_section_id: string | null;
  field_key: string;
  label: string;
  help_text: string | null;
  field_type: MatterCustomFieldType;
  options: string[];
  is_required: boolean;
  is_encrypted: boolean;
  is_masked: boolean;
  is_reportable: boolean;
  position: number;
}

export interface MatterFieldSettings {
  standard_sections: Record<string, string>;
  sections: MatterCustomSection[];
  fields: MatterCustomField[];
}

export interface MatterCustomValue {
  field_id: string;
  value: unknown;
  display_value: string | null;
  has_value: boolean;
  masked: boolean;
  updated_at: string | null;
}

export interface MatterFieldReport {
  field_id: string;
  label: string;
  field_type: MatterCustomFieldType;
  section: string;
  total_matters: number;
  populated: number;
  missing: number;
  completion_rate: number;
  sum: number | null;
  average: number | null;
  values: Array<{ key: string; count: number }>;
  sensitive: boolean;
}

/** Where the matter sits in the Indian court hierarchy. */
export type CourtLevel =
  | 'supreme_court' | 'high_court' | 'district' | 'tribunal'
  | 'consumer' | 'revenue' | 'other';

/** Which side of the cause title — not the same as petitioner/respondent,
 *  since the firm may act for either. */
export type PartySide = 'ours' | 'opposing' | 'other';

export type AdvocateRole =
  | 'senior_counsel' | 'arguing_counsel' | 'advocate_on_record'
  | 'junior' | 'instructing' | 'party_in_person';

export const COURT_LEVEL_LABELS: Record<CourtLevel, string> = {
  supreme_court: 'Supreme Court',
  high_court: 'High Court',
  district: 'District judiciary',
  tribunal: 'Tribunal',
  consumer: 'Consumer forum',
  revenue: 'Revenue court',
  other: 'Other',
};

export const ADVOCATE_ROLE_LABELS: Record<AdvocateRole, string> = {
  senior_counsel: 'Senior Counsel',
  arguing_counsel: 'Arguing Counsel',
  advocate_on_record: 'Advocate on Record',
  junior: 'Junior',
  instructing: 'Instructing Advocate',
  party_in_person: 'Party-in-person',
};

// ─── Team ───────────────────────────────────────────────────────────
export type TeamRole =
  | 'lead_counsel' | 'supervising_partner' | 'senior_counsel' | 'arguing_counsel' | 'advocate_on_record'
  | 'associate' | 'junior' | 'briefing_counsel' | 'paralegal' | 'clerk' | 'other';

export const TEAM_ROLE_LABELS: Record<TeamRole, string> = {
  lead_counsel: 'Lead counsel (in charge)',
  supervising_partner: 'Supervising partner',
  senior_counsel: 'Senior counsel',
  arguing_counsel: 'Arguing counsel',
  advocate_on_record: 'Advocate on Record',
  associate: 'Associate',
  junior: 'Junior',
  briefing_counsel: 'Briefing counsel',
  paralegal: 'Paralegal',
  clerk: 'Clerk',
  other: 'Other',
};

export type TeamEndReason =
  | 'reassigned' | 'left_firm' | 'workload' | 'client_request' | 'conflict' | 'matter_closed' | 'other';

export const TEAM_END_REASON_LABELS: Record<TeamEndReason, string> = {
  reassigned: 'Reassigned',
  left_firm: 'Left the firm',
  workload: 'Workload',
  client_request: 'Client request',
  conflict: 'Conflict of interest',
  matter_closed: 'Matter closed',
  other: 'Other',
};

export type RateBasis =
  | 'hourly' | 'per_hearing' | 'per_day' | 'per_matter' | 'per_drafting' | 'retainer_monthly';

export const RATE_BASIS_LABELS: Record<RateBasis, string> = {
  hourly: 'Per hour',
  per_hearing: 'Per hearing / appearance',
  per_day: 'Per day (outstation / full day)',
  per_matter: 'Per matter (fixed per case)',
  per_drafting: 'Per drafting / opinion / conference',
  retainer_monthly: 'Monthly retainer',
};

export interface Person {
  id: string;
  full_name: string;
  email: string;
}

export interface TeamMember {
  id: string;
  matter_id: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  role: TeamRole;
  from_date: string;
  to_date: string | null;
  end_reason: TeamEndReason | null;
  successor_user_id: string | null;
  successor_name: string | null;
  rate_basis: RateBasis | null;
  rate_amount: string | null;
  card_rate_basis: RateBasis | null;
  card_rate_amount: string | null;
  notes: string | null;
  is_active: boolean;
}

export interface TeamMemberCreate {
  user_id: string;
  role?: TeamRole;
  from_date?: string | null;
  rate_basis?: RateBasis | null;
  rate_amount?: number | null;
  notes?: string | null;
}

export interface TeamHandover {
  effective_from?: string | null;
  reason?: TeamEndReason;
  successor_user_id?: string | null;
  successor_role?: TeamRole | null;
  notes?: string | null;
}

export interface TeamTransfer {
  from_user_id: string;
  to_user_id: string;
  effective_from?: string | null;
  reason?: TeamEndReason;
  matter_ids?: string[] | null;
  notes?: string | null;
}

export interface TeamTransferResult {
  moved: number;
  matter_numbers: string[];
}

/** Another matter where this person was on the other side of one of our parties. */
export interface TeamConflict {
  matter_id: string;
  matter_number: string | null;
  title: string;
  party_name: string;
  kind: 'acted_against_client' | 'acted_for_opponent';
  current: boolean;
}

/** One colleague's load: open matters they are on now, by role. */
export interface WorkloadRow {
  user_id: string;
  full_name: string;
  open_matters: number;
  lead_matters: number;
  roles: Partial<Record<TeamRole, number>>;
  hearings_next_14_days: number;
}

// ─── Fees ───────────────────────────────────────────────────────────
export type FeeBasis = 'fixed' | 'per_hearing' | 'hourly' | 'retainer' | 'milestone' | 'hybrid' | 'pro_bono';

export const FEE_BASIS_LABELS: Record<FeeBasis, string> = {
  fixed: 'Fixed fee (lump sum for the matter)',
  per_hearing: 'Per hearing / appearance',
  hourly: 'Hourly (time-based)',
  retainer: 'Retainer (periodic)',
  milestone: 'Milestone-based (stage-wise)',
  hybrid: 'Hybrid (combination)',
  pro_bono: 'Pro bono',
};

export type RetainerPeriod = 'monthly' | 'quarterly' | 'half_yearly' | 'yearly';

export type MilestoneTrigger =
  | 'advance' | 'on_filing' | 'on_first_hearing' | 'on_pleadings' | 'on_evidence' | 'on_arguments'
  | 'on_judgment' | 'on_closure' | 'on_date' | 'manual';

export const MILESTONE_TRIGGER_LABELS: Record<MilestoneTrigger, string> = {
  advance: 'Advance — on engagement',
  on_filing: 'On filing',
  on_first_hearing: 'On first hearing',
  on_pleadings: 'On completion of pleadings',
  on_evidence: 'At evidence stage',
  on_arguments: 'At final arguments',
  on_judgment: 'On judgment / final order',
  on_closure: 'On closure (settlement, withdrawal, disposal)',
  on_date: 'On a date',
  manual: 'When marked by staff',
};

export type MilestoneStatus = 'pending' | 'due' | 'waived';

export interface Milestone {
  id: string;
  arrangement_id: string;
  sequence: number;
  label: string;
  trigger: MilestoneTrigger;
  amount: string | null;
  percent: string | null;
  due_on: string | null;
  due_days: number;
  status: MilestoneStatus;
  triggered_at: string | null;
  computed_amount: string | null;
}

export interface MilestoneCreate {
  label: string;
  trigger: MilestoneTrigger;
  amount?: number | null;
  percent?: number | null;
  due_on?: string | null;
  due_days?: number;
}

export interface FeeArrangement {
  id: string;
  matter_id: string;
  basis: FeeBasis;
  currency: string;
  fixed_fee: string | null;
  per_hearing_fee: string | null;
  non_effective_hearing_fee: string | null;
  hourly_rate: string | null;
  retainer_amount: string | null;
  retainer_period: RetainerPeriod | null;
  retainer_includes: string | null;
  fee_cap: string | null;
  expenses_billable: boolean;
  gst_applicable: boolean;
  agreed_on: string | null;
  effective_from: string;
  effective_to: string | null;
  terms: string | null;
  created_by: string;
  created_at: string;
  milestones: Milestone[];
  is_active: boolean;
}

export interface FeeArrangementCreate {
  basis: FeeBasis;
  currency?: string;
  fixed_fee?: number | null;
  per_hearing_fee?: number | null;
  non_effective_hearing_fee?: number | null;
  hourly_rate?: number | null;
  retainer_amount?: number | null;
  retainer_period?: RetainerPeriod | null;
  retainer_includes?: string | null;
  fee_cap?: number | null;
  expenses_billable?: boolean;
  gst_applicable?: boolean;
  agreed_on?: string | null;
  effective_from?: string | null;
  terms?: string | null;
  milestones?: MilestoneCreate[];
}

export type FeeEventKind = 'milestone' | 'hearing' | 'hearing_non_effective' | 'retainer' | 'manual';
export type FeeEventStatus = 'unbilled' | 'invoiced' | 'waived';

export const FEE_EVENT_KIND_LABELS: Record<FeeEventKind, string> = {
  milestone: 'Milestone',
  hearing: 'Hearing',
  hearing_non_effective: 'Non-effective hearing',
  retainer: 'Retainer',
  manual: 'Manual',
};

export interface FeeEvent {
  id: string;
  matter_id: string;
  arrangement_id: string | null;
  milestone_id: string | null;
  hearing_id: string | null;
  kind: FeeEventKind;
  description: string;
  occurred_on: string;
  due_on: string | null;
  amount: string;
  currency: string;
  status: FeeEventStatus;
  invoice_id: string | null;
  created_at: string;
}

export interface FeeSummary {
  unbilled_total: string;
  unbilled_count: number;
  invoiced_total: string;
  waived_total: string;
  currency: string;
}

// ─── Counsel rate cards ─────────────────────────────────────────────
export interface CounselRate {
  id: string;
  user_id: string;
  user_name: string | null;
  basis: RateBasis;
  amount: string;
  currency: string;
  effective_from: string;
  effective_to: string | null;
  notes: string | null;
  created_at: string;
  is_current: boolean;
}

export interface RateCard {
  user_id: string;
  full_name: string;
  email: string;
  is_active: boolean;
  rates: CounselRate[];
}

/** The Indian court registry fields carried by a matter. */
export interface CourtRecord {
  cnr_number: string | null;
  case_type: string | null;
  case_year: number | null;
  filing_number: string | null;
  filing_date: string | null;
  registration_number: string | null;
  registration_date: string | null;
  court_level: CourtLevel | null;
  court_establishment: string | null;
  state: string | null;
  district: string | null;
  coram: string | null;
  cause_title: string | null;
  acts: string[];
  sections: string[];
  next_hearing_date: string | null;
  last_hearing_date: string | null;
  hearing_purpose: string | null;
  disposal_date: string | null;
  disposal_nature: string | null;
}

export interface Matter extends CourtRecord {
  id: string;
  matter_number: string;
  title: string;
  client_id: string | null;
  client_name: string;
  lead_counsel_id: string | null;
  lead_counsel_name: string | null;
  matter_type: MatterType;
  status: MatterStatus;
  stage: MatterStage;
  priority: Priority;
  practice_area: string | null;
  court: string | null;
  case_number: string | null;
  description: string | null;
  opened_on: string | null;
  limitation_date: string | null;
  assigned_to: string | null;
  created_by: string;
  created_at: string;
  ecourts_synced_at: string | null;
  ecourts_source: string | null;
}

export interface Advocate {
  id: string;
  name: string;
  side: PartySide;
  role: AdvocateRole;
  bar_enrolment_number: string | null;
  firm: string | null;
  party_represented: string | null;
  email: string | null;
  phone: string | null;
  user_id: string | null;
  is_lead: boolean;
  notes: string | null;
}

/** A case fetched from eCourts, before it is filed as a matter. */
export interface ECourtsCase extends CourtRecord {
  case_number: string | null;
  status: string | null;
  stage: string | null;
  parties: { name: string; role: string; position: number | null }[];
  advocates: { name: string; appears_for: string; bar_enrolment_number: string | null }[];
  source: string;
}

export interface ECourtsLookup {
  cnr_number?: string;
  case_type?: string;
  case_number?: string;
  case_year?: number;
  state?: string;
  district?: string;
  court_establishment?: string;
}

export interface TimelineEntry {
  kind: 'matter' | 'hearing' | 'task' | 'task_done' | 'note';
  at: string;
  title: string;
  detail: string | null;
  status: string | null;
}

export interface Party {
  id: string;
  name: string;
  role: string;
  contact: string | null;
  side: PartySide;
  position: number | null;
}

export interface Hearing {
  id: string;
  matter_id: string;
  scheduled_on: string;
  court: string | null;
  /** Courtroom ("12") and cause-list item ("34"). */
  court_room?: string | null;
  item_number?: string | null;
  judge: string | null;
  purpose: string | null;
  status: HearingStatus;
  notes: string | null;
  outcome: string | null;
  next_date: string | null;
}

export interface Task {
  id: string;
  matter_id: string;
  title: string;
  due_on: string | null;
  status: TaskStatus;
  assigned_to: string | null;
  completed_at: string | null;
}

export interface Note {
  id: string;
  matter_id: string;
  author_id: string;
  body: string;
  created_at: string;
}

export interface MatterAuthority {
  id: string;
  matter_id: string;
  kind: 'judgment' | 'statute';
  judgment_id: string | null;
  act_id: string | null;
  reference: string;
  paragraph_no: number | null;
  quotation: string | null;
  proposition: string | null;
  stance: 'favourable' | 'adverse' | 'distinguish' | 'background' | 'pending_review';
  source_url: string | null;
  created_by: string;
  created_at: string;
}

export interface MatterDetail extends Matter {
  parties: Party[];
  advocates: Advocate[];
  hearings: Hearing[];
  tasks: Task[];
  notes: Note[];
  team: TeamMember[];
  fee_arrangements: FeeArrangement[];
  fee_events: FeeEvent[];
  authorities: MatterAuthority[];
}

export interface MatterCreate extends Partial<CourtRecord> {
  title: string;
  client_id?: string | null;
  client_name?: string | null;
  lead_counsel_id?: string | null;
  team?: TeamMemberCreate[];
  matter_type?: MatterType;
  practice_area?: string | null;
  court?: string | null;
  case_number?: string | null;
  description?: string | null;
  limitation_date?: string | null;
}

export interface AdvocateCreate {
  name: string;
  side: PartySide;
  role?: AdvocateRole;
  bar_enrolment_number?: string | null;
  firm?: string | null;
  party_represented?: string | null;
  email?: string | null;
  phone?: string | null;
  is_lead?: boolean;
  notes?: string | null;
}

export interface ECourtsImport extends ECourtsLookup {
  client_id?: string | null;
  client_name?: string | null;
  lead_counsel_id?: string | null;
  our_side_role?: string;
  matter_type?: MatterType;
}

export interface MatterUpdate {
  title?: string;
  client_id?: string | null;
  client_name?: string;
  status?: MatterStatus;
  stage?: MatterStage;
  priority?: Priority;
  court?: string | null;
  limitation_date?: string | null;
}

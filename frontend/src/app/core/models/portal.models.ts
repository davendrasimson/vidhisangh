/** Client portal API contracts (mirrors the backend portal module). */

export type ApprovalStatus = 'pending' | 'approved' | 'rejected';

export interface PortalAccess {
  id: string;
  matter_id: string;
  client_name: string;
  client_email: string;
  token: string;
  is_active: boolean;
  created_at: string;
}

export interface PortalUpdate {
  id: string;
  title: string;
  body: string;
  created_at: string;
}

export interface PortalApproval {
  id: string;
  title: string;
  description: string | null;
  status: ApprovalStatus;
  response_note: string | null;
  responded_at: string | null;
  created_at: string;
}

export interface PortalHearing {
  scheduled_on: string;
  court: string | null;
  purpose: string | null;
  status: string;
}

export interface PortalDocument {
  id: string;
  name: string;
  size: number;
  version_count: number;
  updated_at: string;
}

export interface PortalInvoice {
  id: string;
  invoice_number: string;
  status: string;
  issue_date: string | null;
  due_date: string | null;
  total: number;
  amount_paid: number;
}

export interface PortalView {
  client_name: string;
  matter_number: string;
  matter_title: string;
  status: string;
  stage: string;
  court: string | null;
  opened_on: string | null;
  hearings: PortalHearing[];
  updates: PortalUpdate[];
  approvals: PortalApproval[];
  documents: PortalDocument[];
  invoices: PortalInvoice[];
}

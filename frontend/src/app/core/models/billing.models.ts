/** Billing API contracts (mirrors the backend billing module). */

export type InvoiceStatus = 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled';
export type InvoiceDocumentType = 'proforma' | 'tax_invoice' | 'credit_note';
/** How often a recurring invoice (a retainer, a monthly compliance fee) is raised again. */
export type InvoiceRecurrence = 'monthly' | 'quarterly' | 'yearly';

export interface LineItem {
  id: string;
  description: string;
  quantity: string | number;
  unit_price: string | number;
  amount: string | number;
}

/** The client's tax position as it stood when the invoice was made. */
export interface InvoiceTaxFields {
  client_gstin?: string | null;
  gst_treatment?: string | null;
  place_of_supply_code?: string | null;
  place_of_supply?: string | null;
  supplier_state_code?: string | null;
  reverse_charge?: boolean;
  tax_split?: { igst?: string | number; cgst?: string | number; sgst?: string | number } | null;
  tds_section?: string | null;
  tds_rate?: string | number | null;
  tds_amount?: string | number | null;
}

export interface Invoice extends InvoiceTaxFields {
  id: string;
  invoice_number: string;
  document_type: InvoiceDocumentType;
  client_name: string;
  client_id: string | null;
  matter_id: string | null;
  status: InvoiceStatus;
  issue_date: string | null;
  due_date: string | null;
  currency: string;
  tax_rate: string | number;
  subtotal: string | number;
  tax_amount: string | number;
  total: string | number;
  amount_paid: string | number;
  notes: string | null;
  verification_code: string;
  payment_token: string;
  source_proforma_id: string | null;
  converted_invoice_id: string | null;
  /** Set on a template: the nightly sweep raises a draft copy on next_issue_on until recur_until. */
  recurrence?: InvoiceRecurrence | null;
  recur_until?: string | null;
  next_issue_on?: string | null;
  /** Set on a copy: the template it was raised from. */
  recurring_from_id?: string | null;
  next_follow_up_on: string | null;
  last_follow_up_at: string | null;
  created_at: string;
}

export interface InvoiceDetail extends Invoice {
  line_items: LineItem[];
  follow_ups: InvoiceFollowUp[];
  receipts: BillingReceipt[];
}

export interface LineItemCreate {
  description: string;
  quantity: number;
  unit_price: number;
}

export interface InvoiceCreate {
  client_name: string;
  client_id?: string | null;
  matter_id?: string | null;
  /** Left out / null: from the client master. */
  tax_rate?: number | null;
  due_date?: string | null;
  notes?: string | null;
  line_items?: LineItemCreate[];
  document_type?: InvoiceDocumentType;
  recurrence?: InvoiceRecurrence | null;
  recur_until?: string | null;
}

export interface InvoiceFollowUp {
  id: string;
  invoice_id: string;
  channel: string;
  remark: string;
  outcome: string | null;
  next_follow_up_on: string | null;
  created_at: string;
}

export interface FollowUpCreate {
  channel: string;
  remark: string;
  outcome?: string | null;
  next_follow_up_on?: string | null;
}

export interface BillingReceipt {
  id: string;
  receipt_number: string;
  invoice_id: string;
  payment_id: string | null;
  amount: string | number;
  received_on: string;
  payment_method: string;
  reference: string | null;
  remarks: string | null;
  verification_code: string;
  created_at: string;
}

export interface ReceiptCreate {
  amount: number;
  received_on?: string | null;
  payment_method: string;
  reference?: string | null;
  remarks?: string | null;
}

export interface BillingSummary {
  pending_count: number;
  pending_total: string | number;
  overdue_count: number;
  follow_ups_due: number;
  receipts_total: string | number;
}

export interface BillingBranding {
  template_id: 'classic' | 'modern' | 'minimal';
  legal_name: string;
  address: string;
  email: string;
  phone: string;
  gstin: string;
  pan: string;
  logo_url: string;
  accent_color: string;
  bank_details: string;
  payment_terms: string;
  footer: string;
  signature_name: string;
  proforma_prefix: string;
  invoice_prefix: string;
  credit_note_prefix: string;
  receipt_prefix: string;
}

export interface PublicInvoice extends InvoiceTaxFields {
  invoice_number: string;
  document_type: InvoiceDocumentType;
  client_name: string;
  status: InvoiceStatus;
  issue_date: string | null;
  due_date: string | null;
  currency: string;
  subtotal: string | number;
  tax_rate: string | number;
  tax_amount: string | number;
  total: string | number;
  amount_paid: string | number;
  notes: string | null;
  verification_code: string;
  line_items: LineItem[];
  branding: BillingBranding;
}

export interface BillingVerification {
  valid: boolean;
  document_type: InvoiceDocumentType | 'receipt';
  number: string;
  firm: string;
  client_name?: string;
  issue_date?: string;
  received_on?: string;
  total: string | number;
  currency: string;
  status: string;
}

export type TimeEntryStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'billed';

export interface TimeEntry {
  id: string;
  user_id: string;
  counsel_name: string;
  matter_id: string | null;
  matter_number: string | null;
  client_id: string | null;
  client_name: string | null;
  invoice_id: string | null;
  work_date: string;
  duration_minutes: number;
  description: string;
  activity_type: string;
  billable: boolean;
  hourly_rate: string | number;
  amount: string | number;
  status: TimeEntryStatus;
  source: 'manual' | 'import';
  rejection_reason: string | null;
  created_at: string;
}

export interface TimeEntryCreate {
  matter_id?: string | null;
  client_id?: string | null;
  work_date: string;
  duration_minutes: number;
  description: string;
  activity_type?: string;
  billable?: boolean;
}

export interface TimeImportRow {
  row_number: number;
  work_date: string | null;
  counsel_email: string;
  matter_number: string;
  client_name: string;
  duration_minutes: number;
  description: string;
  activity_type: string;
  billable: boolean;
  errors: string[];
}

export interface TimeImportPreview {
  filename: string;
  rows: TimeImportRow[];
  valid_count: number;
  error_count: number;
}

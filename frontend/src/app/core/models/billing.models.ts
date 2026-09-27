/** Billing API contracts (mirrors the backend billing module). */

export type InvoiceStatus = 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled';

export interface LineItem {
  id: string;
  description: string;
  quantity: string | number;
  unit_price: string | number;
  amount: string | number;
}

export interface Invoice {
  id: string;
  invoice_number: string;
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
  created_at: string;
}

export interface InvoiceDetail extends Invoice {
  line_items: LineItem[];
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
  tax_rate?: number;
  due_date?: string | null;
  notes?: string | null;
  line_items?: LineItemCreate[];
}

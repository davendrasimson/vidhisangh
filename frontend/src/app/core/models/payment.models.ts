/** Payments API contracts (mirrors the backend payments module). */

export type PaymentStatus = 'created' | 'paid' | 'failed' | 'refunded';

export interface Payment {
  id: string;
  amount: number; // smallest unit (paise)
  currency: string;
  status: PaymentStatus;
  provider: string;
  provider_order_id: string;
  provider_payment_id: string | null;
  receipt: string | null;
  description: string | null;
  matter_id: string | null;
  invoice_id: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface OrderResponse {
  payment_id: string;
  order_id: string;
  key_id: string;
  amount: number;
  currency: string;
  provider: string;
}

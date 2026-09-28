import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  BillingBranding,
  BillingReceipt,
  BillingSummary,
  BillingVerification,
  FollowUpCreate,
  Invoice,
  InvoiceCreate,
  InvoiceDetail,
  InvoiceStatus,
  InvoiceFollowUp,
  LineItemCreate,
  PublicInvoice,
  ReceiptCreate,
} from '@core/models/billing.models';
import type { CheckoutResult } from './payment.service';
import { OrderResponse } from '@core/models/payment.models';

@Injectable({ providedIn: 'root' })
export class BillingService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/billing`;

  list(status?: InvoiceStatus, extra: { clientId?: string; matterId?: string } = {}): Observable<Invoice[]> {
    const params: Record<string, string> = {};
    if (status) params['status'] = status;
    if (extra.clientId) params['client_id'] = extra.clientId;
    if (extra.matterId) params['matter_id'] = extra.matterId;
    return this.http.get<Invoice[]>(`${this.api}/invoices`, { params });
  }

  pending(): Observable<Invoice[]> {
    return this.http.get<Invoice[]>(`${this.api}/invoices/pending`);
  }

  summary(): Observable<BillingSummary> {
    return this.http.get<BillingSummary>(`${this.api}/summary`);
  }

  followUps(): Observable<InvoiceFollowUp[]> {
    return this.http.get<InvoiceFollowUp[]>(`${this.api}/follow-ups`);
  }

  receipts(): Observable<BillingReceipt[]> {
    return this.http.get<BillingReceipt[]>(`${this.api}/receipts`);
  }

  get(id: string): Observable<InvoiceDetail> {
    return this.http.get<InvoiceDetail>(`${this.api}/invoices/${id}`);
  }

  create(payload: InvoiceCreate): Observable<InvoiceDetail> {
    return this.http.post<InvoiceDetail>(`${this.api}/invoices`, payload);
  }

  prepareMatterInvoice(matterId: string): Observable<InvoiceDetail> {
    return this.http.post<InvoiceDetail>(`${this.api}/matters/${matterId}/prepare-invoice`, {});
  }

  update(id: string, patch: Partial<Invoice>): Observable<InvoiceDetail> {
    return this.http.patch<InvoiceDetail>(`${this.api}/invoices/${id}`, patch);
  }

  addLineItem(id: string, item: LineItemCreate): Observable<InvoiceDetail> {
    return this.http.post<InvoiceDetail>(`${this.api}/invoices/${id}/line-items`, item);
  }

  removeLineItem(itemId: string): Observable<InvoiceDetail> {
    return this.http.delete<InvoiceDetail>(`${this.api}/line-items/${itemId}`);
  }

  pay(id: string): Observable<OrderResponse> {
    return this.http.post<OrderResponse>(`${this.api}/invoices/${id}/pay`, {});
  }

  reconcile(id: string): Observable<InvoiceDetail> {
    return this.http.post<InvoiceDetail>(`${this.api}/invoices/${id}/reconcile`, {});
  }

  addFollowUp(id: string, payload: FollowUpCreate): Observable<InvoiceDetail> {
    return this.http.post<InvoiceDetail>(`${this.api}/invoices/${id}/follow-ups`, payload);
  }

  recordReceipt(id: string, payload: ReceiptCreate): Observable<InvoiceDetail> {
    return this.http.post<InvoiceDetail>(`${this.api}/invoices/${id}/receipts`, payload);
  }

  branding(): Observable<BillingBranding> {
    return this.http.get<BillingBranding>(`${this.api}/settings/branding`);
  }

  saveBranding(payload: BillingBranding): Observable<BillingBranding> {
    return this.http.put<BillingBranding>(`${this.api}/settings/branding`, payload);
  }

  publicInvoice(token: string): Observable<PublicInvoice> {
    return this.http.get<PublicInvoice>(`${this.api}/public/invoices/${encodeURIComponent(token)}`);
  }

  publicPay(token: string): Observable<OrderResponse> {
    return this.http.post<OrderResponse>(`${this.api}/public/invoices/${encodeURIComponent(token)}/pay`, {});
  }

  publicVerifyPayment(token: string, paymentId: string, result: CheckoutResult): Observable<PublicInvoice> {
    return this.http.post<PublicInvoice>(
      `${this.api}/public/invoices/${encodeURIComponent(token)}/payments/${paymentId}/verify`, result,
    );
  }

  verifyDocument(code: string): Observable<BillingVerification> {
    return this.http.get<BillingVerification>(`${this.api}/verify/${encodeURIComponent(code)}`);
  }

  qrUrl(code: string): string {
    return `${this.api}/verify/${encodeURIComponent(code)}/qr`;
  }
}

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  Invoice,
  InvoiceCreate,
  InvoiceDetail,
  InvoiceStatus,
  LineItemCreate,
} from '@core/models/billing.models';
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
}

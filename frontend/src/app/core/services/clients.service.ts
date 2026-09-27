import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  Client,
  ClientCreate,
  ClientFields,
  ClientKind,
  ClientStatus,
  ClientSummary,
  KycPublicView,
  KycRequest,
  KycRequestDetail,
  KycSubmitResult,
  ReferenceData,
} from '@core/models/clients.models';

@Injectable({ providedIn: 'root' })
export class ClientsService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/clients`;
  private readonly kycApi = `${environment.apiBaseUrl}/kyc`;

  reference(): Observable<ReferenceData> {
    return this.http.get<ReferenceData>(`${this.api}/reference`);
  }

  list(opts: { q?: string; kind?: ClientKind | ''; status?: ClientStatus | '' } = {}): Observable<ClientSummary[]> {
    const params: Record<string, string> = {};
    if (opts.q) params['q'] = opts.q;
    if (opts.kind) params['kind'] = opts.kind;
    if (opts.status) params['status'] = opts.status;
    return this.http.get<ClientSummary[]>(this.api, { params });
  }

  get(id: string): Observable<Client> {
    return this.http.get<Client>(`${this.api}/${id}`);
  }

  create(payload: ClientCreate): Observable<Client> {
    return this.http.post<Client>(this.api, payload);
  }

  update(id: string, payload: ClientFields & { kind?: ClientKind }): Observable<Client> {
    return this.http.patch<Client>(`${this.api}/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${id}`);
  }

  // ── KYC (firm side) ──────────────────────────────────────────
  kycRequests(clientId: string): Observable<KycRequest[]> {
    return this.http.get<KycRequest[]>(`${this.api}/${clientId}/kyc`);
  }

  sendKyc(clientId: string, body: { send_to_email?: string | null; send_to_mobile?: string | null; message?: string | null; expires_in_days?: number }): Observable<KycRequest> {
    return this.http.post<KycRequest>(`${this.api}/${clientId}/kyc`, body);
  }

  kycRequest(clientId: string, requestId: string): Observable<KycRequestDetail> {
    return this.http.get<KycRequestDetail>(`${this.api}/${clientId}/kyc/${requestId}`);
  }

  applyKyc(clientId: string, requestId: string, fields: string[] | null = null, markVerified = true): Observable<Client> {
    return this.http.post<Client>(`${this.api}/${clientId}/kyc/${requestId}/apply`, { fields, mark_verified: markVerified });
  }

  cancelKyc(clientId: string, requestId: string): Observable<KycRequest> {
    return this.http.post<KycRequest>(`${this.api}/${clientId}/kyc/${requestId}/cancel`, {});
  }

  // ── KYC (public, token) ──────────────────────────────────────
  kycView(token: string): Observable<KycPublicView> {
    return this.http.get<KycPublicView>(`${this.kycApi}/${encodeURIComponent(token)}`);
  }

  kycSubmit(token: string, body: ClientFields & { declaration_accepted: boolean }): Observable<KycSubmitResult> {
    return this.http.post<KycSubmitResult>(`${this.kycApi}/${encodeURIComponent(token)}`, body);
  }
}

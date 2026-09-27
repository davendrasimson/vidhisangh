import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { ClientEraseResult, ConsentEvent, ConsentPurpose, LegalHold } from './client-privacy.models';

/** Client-side privacy calls: consent ledger, export, legal holds, erasure. */
@Injectable({ providedIn: 'root' })
export class ClientPrivacyService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/clients`;

  consents(clientId: string): Observable<ConsentEvent[]> {
    return this.http.get<ConsentEvent[]>(`${this.api}/${clientId}/consents`);
  }

  recordConsent(clientId: string, purpose: ConsentPurpose, granted: boolean, note?: string): Observable<ConsentEvent> {
    return this.http.post<ConsentEvent>(`${this.api}/${clientId}/consents`, { purpose, granted, note: note || null });
  }

  legalHolds(clientId: string): Observable<LegalHold[]> {
    return this.http.get<LegalHold[]>(`${this.api}/${clientId}/legal-holds`);
  }

  /** The JSON bundle as a Blob so the browser can save it. */
  exportBlob(clientId: string): Observable<Blob> {
    return this.http.get(`${this.api}/${clientId}/export`, { responseType: 'blob' });
  }

  erase(clientId: string, opts: { overrideLegalHold?: boolean; reason?: string } = {}): Observable<ClientEraseResult> {
    let params = new HttpParams().set('erase', 'true');
    if (opts.overrideLegalHold) params = params.set('override_legal_hold', 'true');
    if (opts.reason) params = params.set('reason', opts.reason);
    return this.http.delete<ClientEraseResult>(`${this.api}/${clientId}`, { params });
  }
}

/** Trigger a browser download of a Blob. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

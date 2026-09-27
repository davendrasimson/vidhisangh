import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  PortalAccess,
  PortalApproval,
  PortalUpdate,
  PortalView,
} from '@core/models/portal.models';

/** Firm-side portal management + client-side (token) access. */
@Injectable({ providedIn: 'root' })
export class PortalService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/portal`;

  // ── Firm-side ─────────────────────────────────────────────────
  listAccess(matterId: string): Observable<PortalAccess[]> {
    return this.http.get<PortalAccess[]>(`${this.api}/access`, { params: { matter_id: matterId } });
  }

  grantAccess(matter_id: string, client_name: string, client_email: string): Observable<PortalAccess> {
    return this.http.post<PortalAccess>(`${this.api}/access`, { matter_id, client_name, client_email });
  }

  revoke(accessId: string): Observable<PortalAccess> {
    return this.http.post<PortalAccess>(`${this.api}/access/${accessId}/revoke`, {});
  }

  postUpdate(matterId: string, title: string, body: string): Observable<PortalUpdate> {
    return this.http.post<PortalUpdate>(`${this.api}/matters/${matterId}/updates`, { title, body });
  }

  requestApproval(matterId: string, title: string, description?: string): Observable<PortalApproval> {
    return this.http.post<PortalApproval>(`${this.api}/matters/${matterId}/approvals`, { title, description });
  }

  approvals(matterId: string): Observable<PortalApproval[]> {
    return this.http.get<PortalApproval[]>(`${this.api}/matters/${matterId}/approvals`);
  }

  sharedDocumentIds(matterId: string): Observable<string[]> {
    return this.http.get<string[]>(`${this.api}/matters/${matterId}/documents`);
  }

  shareDocument(matterId: string, documentId: string): Observable<void> {
    return this.http.post<void>(`${this.api}/matters/${matterId}/documents/${documentId}`, {});
  }

  unshareDocument(matterId: string, documentId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/matters/${matterId}/documents/${documentId}`);
  }

  // ── Client-side (token) ───────────────────────────────────────
  view(token: string): Observable<PortalView> {
    return this.http.get<PortalView>(`${this.api}/client/${token}`);
  }

  respond(token: string, approvalId: string, approve: boolean, note?: string): Observable<PortalApproval> {
    return this.http.post<PortalApproval>(
      `${this.api}/client/${token}/approvals/${approvalId}/respond`,
      { approve, note },
    );
  }

  downloadUrl(token: string, documentId: string): string {
    return `${this.api}/client/${token}/documents/${documentId}/download`;
  }

  clientDownload(token: string, documentId: string): Observable<Blob> {
    return this.http.get(this.downloadUrl(token, documentId), { responseType: 'blob' });
  }
}

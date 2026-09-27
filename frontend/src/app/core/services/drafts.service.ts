import { HttpClient, HttpContext } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { SILENT_ERRORS } from '@core/interceptors/error.interceptor';
import { DocFile } from '@core/models/documents.models';
import {
  Draft,
  DraftCreate,
  DraftSummary,
  DraftUpdate,
  DraftVersion,
  DraftVersionDetail,
} from '@core/models/drafts.models';

@Injectable({ providedIn: 'root' })
export class DraftsService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/drafts`;

  list(opts: { matterId?: string | null; clientId?: string | null; q?: string } = {}): Observable<DraftSummary[]> {
    const params: Record<string, string> = {};
    if (opts.matterId) params['matter_id'] = opts.matterId;
    if (opts.clientId) params['client_id'] = opts.clientId;
    if (opts.q) params['q'] = opts.q;
    return this.http.get<DraftSummary[]>(this.api, { params });
  }

  get(id: string): Observable<Draft> {
    return this.http.get<Draft>(`${this.api}/${id}`);
  }

  create(payload: DraftCreate): Observable<Draft> {
    return this.http.post<Draft>(this.api, payload);
  }

  /** Autosave: only the fields that changed. Failures are reported by the
   *  editor's own status line, not the global toast. */
  update(id: string, payload: DraftUpdate): Observable<Draft> {
    return this.http.patch<Draft>(`${this.api}/${id}`, payload, {
      context: new HttpContext().set(SILENT_ERRORS, true),
    });
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${id}`);
  }

  versions(id: string): Observable<DraftVersion[]> {
    return this.http.get<DraftVersion[]>(`${this.api}/${id}/versions`);
  }

  saveVersion(id: string, note: string | null): Observable<DraftVersion> {
    return this.http.post<DraftVersion>(`${this.api}/${id}/versions`, { note });
  }

  version(id: string, versionId: string): Observable<DraftVersionDetail> {
    return this.http.get<DraftVersionDetail>(`${this.api}/${id}/versions/${versionId}`);
  }

  restore(id: string, versionId: string): Observable<Draft> {
    return this.http.post<Draft>(`${this.api}/${id}/versions/${versionId}/restore`, {});
  }

  /** Word document built server-side from the draft's structure. */
  exportDocx(id: string): Observable<Blob> {
    return this.http.get(`${this.api}/${id}/export.docx`, { responseType: 'blob' });
  }

  /** File the .docx into the document library (a new version if already filed). */
  fileToLibrary(id: string, folderId: string | null, comment?: string): Observable<DocFile> {
    return this.http.post<DocFile>(`${this.api}/${id}/file`, { folder_id: folderId, comment: comment ?? null });
  }
}

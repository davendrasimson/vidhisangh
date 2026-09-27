import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { DocFile, DocFolder, DocVersion } from '@core/models/documents.models';

/** Mirrors the API's VS_MAX_UPLOAD_BYTES / nginx client_max_body_size (25 MiB). */
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

export class UploadTooLargeError extends Error {
  constructor(public readonly size: number, public readonly limit: number = MAX_UPLOAD_BYTES) {
    super(`This file is ${(size / 1024 / 1024).toFixed(1)} MB; the limit is ${limit / 1024 / 1024} MB.`);
    this.name = 'UploadTooLargeError';
  }
}

/** Refuse oversize files before any bytes leave the browser (the server enforces the same cap with 413). */
function assertUploadSize(file: File): void {
  if (file.size > MAX_UPLOAD_BYTES) throw new UploadTooLargeError(file.size);
}

@Injectable({ providedIn: 'root' })
export class DocumentsService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/documents`;

  // ── Folders ───────────────────────────────────────────────────
  folders(parentId?: string | null): Observable<DocFolder[]> {
    const params: Record<string, string> = {};
    if (parentId) params['parent_id'] = parentId;
    return this.http.get<DocFolder[]>(`${this.api}/folders`, { params });
  }

  createFolder(name: string, parent_id?: string | null): Observable<DocFolder> {
    return this.http.post<DocFolder>(`${this.api}/folders`, { name, parent_id: parent_id ?? null });
  }

  // ── Documents ─────────────────────────────────────────────────
  list(opts: { folderId?: string | null; matterId?: string; clientId?: string | null; q?: string } = {}): Observable<DocFile[]> {
    const params: Record<string, string> = {};
    if (opts.folderId) params['folder_id'] = opts.folderId;
    if (opts.matterId) params['matter_id'] = opts.matterId;
    if (opts.clientId) params['client_id'] = opts.clientId;
    if (opts.q) params['q'] = opts.q;
    return this.http.get<DocFile[]>(this.api, { params });
  }

  get(id: string): Observable<DocFile> {
    return this.http.get<DocFile>(`${this.api}/${id}`);
  }

  upload(file: File, name?: string, folderId?: string | null, matterId?: string, clientId?: string | null): Observable<DocFile> {
    assertUploadSize(file);
    const form = new FormData();
    form.append('file', file);
    if (name) form.append('name', name);
    if (folderId) form.append('folder_id', folderId);
    if (matterId) form.append('matter_id', matterId);
    if (clientId) form.append('client_id', clientId);
    return this.http.post<DocFile>(this.api, form);
  }

  /** Link a document to a client (null = no client). */
  setClient(id: string, clientId: string | null): Observable<DocFile> {
    return this.http.patch<DocFile>(`${this.api}/${id}`, { client_id: clientId });
  }

  addVersion(id: string, file: File, comment?: string): Observable<DocFile> {
    assertUploadSize(file);
    const form = new FormData();
    form.append('file', file);
    if (comment) form.append('comment', comment);
    return this.http.post<DocFile>(`${this.api}/${id}/versions`, form);
  }

  versions(id: string): Observable<DocVersion[]> {
    return this.http.get<DocVersion[]>(`${this.api}/${id}/versions`);
  }

  download(id: string): Observable<Blob> {
    return this.http.get(`${this.api}/${id}/download`, { responseType: 'blob' });
  }

  downloadVersion(versionId: string): Observable<Blob> {
    return this.http.get(`${this.api}/versions/${versionId}/download`, { responseType: 'blob' });
  }

  checkout(id: string): Observable<DocFile> {
    return this.http.post<DocFile>(`${this.api}/${id}/checkout`, {});
  }

  checkin(id: string): Observable<DocFile> {
    return this.http.post<DocFile>(`${this.api}/${id}/checkin`, {});
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${id}`);
  }
}

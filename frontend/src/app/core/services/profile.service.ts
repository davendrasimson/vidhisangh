import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  BarVerificationRequest,
  ProfileDetail,
  ProfileMasters,
  ProfileUpdate,
} from '@core/models/profile.models';

@Injectable({ providedIn: 'root' })
export class ProfileService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/profiles`;

  myProfile(): Observable<ProfileDetail> {
    return this.http.get<ProfileDetail>(`${this.api}/me`);
  }

  masters(): Observable<ProfileMasters> {
    return this.http.get<ProfileMasters>(`${this.api}/masters`);
  }

  getProfile(userId: string): Observable<ProfileDetail> {
    return this.http.get<ProfileDetail>(`${this.api}/${userId}`);
  }

  update(patch: ProfileUpdate): Observable<ProfileDetail> {
    return this.http.put<ProfileDetail>(`${this.api}/me`, patch);
  }

  requestVerification(payload: BarVerificationRequest): Observable<unknown> {
    return this.http.post(`${this.api}/me/verification`, payload);
  }

  endorse(userId: string, skill: string): Observable<unknown> {
    return this.http.post(`${this.api}/${userId}/endorsements`, { skill });
  }

  recommend(userId: string, body: string, relationship_context?: string): Observable<unknown> {
    return this.http.post(`${this.api}/${userId}/recommendations`, {
      body,
      relationship_context,
    });
  }

  // ── Digital visiting card ─────────────────────────────────────
  qrSvg(): Observable<string> {
    return this.http.get(`${this.api}/me/qr`, { responseType: 'text' });
  }

  vcard(): Observable<Blob> {
    return this.http.get(`${this.api}/me/vcard`, { responseType: 'blob' });
  }
}

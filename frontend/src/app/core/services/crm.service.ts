import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  ActivityType,
  Lead,
  LeadActivity,
  LeadCreate,
  LeadDetail,
  LeadStatus,
  PipelineColumn,
  SourceStat,
} from '@core/models/crm.models';

@Injectable({ providedIn: 'root' })
export class CrmService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/crm`;

  pipeline(): Observable<PipelineColumn[]> {
    return this.http.get<PipelineColumn[]>(`${this.api}/pipeline`);
  }

  sourceAnalytics(): Observable<SourceStat[]> {
    return this.http.get<SourceStat[]>(`${this.api}/analytics/sources`);
  }

  get(id: string): Observable<LeadDetail> {
    return this.http.get<LeadDetail>(`${this.api}/leads/${id}`);
  }

  create(payload: LeadCreate): Observable<Lead> {
    return this.http.post<Lead>(`${this.api}/leads`, payload);
  }

  update(id: string, patch: Partial<Lead>): Observable<Lead> {
    return this.http.patch<Lead>(`${this.api}/leads/${id}`, patch);
  }

  setStatus(id: string, status: LeadStatus): Observable<Lead> {
    return this.http.patch<Lead>(`${this.api}/leads/${id}`, { status });
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/leads/${id}`);
  }

  addActivity(
    leadId: string,
    body: { type: ActivityType; subject?: string; body?: string; due_on?: string | null },
  ): Observable<LeadActivity> {
    return this.http.post<LeadActivity>(`${this.api}/leads/${leadId}/activities`, body);
  }

  completeActivity(activityId: string, done = true): Observable<LeadActivity> {
    return this.http.post<LeadActivity>(
      `${this.api}/activities/${activityId}/complete`, {}, { params: { done } },
    );
  }

  convert(leadId: string): Observable<{ matter_id: string }> {
    return this.http.post<{ matter_id: string }>(`${this.api}/leads/${leadId}/convert`, {});
  }
}

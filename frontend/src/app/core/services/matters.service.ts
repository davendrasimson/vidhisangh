import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  Advocate,
  AdvocateCreate,
  ECourtsCase,
  ECourtsImport,
  ECourtsLookup,
  FeeArrangement,
  FeeArrangementCreate,
  FeeEvent,
  FeeEventStatus,
  FeeSummary,
  Hearing,
  Matter,
  MatterCreate,
  MatterDetail,
  MatterStatus,
  MatterUpdate,
  Milestone,
  Note,
  Party,
  Person,
  Task,
  TeamHandover,
  TeamMember,
  TeamMemberCreate,
  TeamTransfer,
  TeamTransferResult,
  TimelineEntry,
  MatterAuthority,
  MatterCustomField,
  MatterCustomSection,
  MatterCustomValue,
  MatterFieldSettings,
  MatterFieldReport,
} from '@core/models/matters.models';

@Injectable({ providedIn: 'root' })
export class MattersService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/matters`;
  private readonly fieldApi = `${environment.apiBaseUrl}/matter-fields`;

  fieldSettings(): Observable<MatterFieldSettings> {
    return this.http.get<MatterFieldSettings>(`${this.fieldApi}/settings`);
  }

  createFieldSection(payload: { name: string; description?: string | null; position?: number }): Observable<MatterCustomSection> {
    return this.http.post<MatterCustomSection>(`${this.fieldApi}/sections`, payload);
  }

  deleteFieldSection(id: string): Observable<void> {
    return this.http.delete<void>(`${this.fieldApi}/sections/${id}`);
  }

  createCustomField(payload: Partial<MatterCustomField> & { label: string; field_type: string; section_key: string }): Observable<MatterCustomField> {
    return this.http.post<MatterCustomField>(`${this.fieldApi}/fields`, payload);
  }

  updateCustomField(id: string, payload: Partial<MatterCustomField>): Observable<MatterCustomField> {
    return this.http.patch<MatterCustomField>(`${this.fieldApi}/fields/${id}`, payload);
  }

  deleteCustomField(id: string): Observable<void> {
    return this.http.delete<void>(`${this.fieldApi}/fields/${id}`);
  }

  customValues(matterId: string): Observable<MatterCustomValue[]> {
    return this.http.get<MatterCustomValue[]>(`${this.fieldApi}/matters/${matterId}/values`);
  }

  saveCustomValues(matterId: string, values: Array<{ field_id: string; value: unknown }>): Observable<MatterCustomValue[]> {
    return this.http.put<MatterCustomValue[]>(`${this.fieldApi}/matters/${matterId}/values`, { values });
  }

  revealCustomValue(matterId: string, fieldId: string): Observable<MatterCustomValue> {
    return this.http.get<MatterCustomValue>(`${this.fieldApi}/matters/${matterId}/values/${fieldId}/reveal`);
  }

  customFieldReport(): Observable<MatterFieldReport[]> {
    return this.http.get<MatterFieldReport[]>(`${this.fieldApi}/report`);
  }

  list(status?: MatterStatus, page = 1, size = 50, extra: { client_id?: string; user_id?: string } = {}): Observable<Matter[]> {
    const params: Record<string, string | number> = { page, size };
    if (status) params['status'] = status;
    if (extra.client_id) params['client_id'] = extra.client_id;
    if (extra.user_id) params['user_id'] = extra.user_id;
    return this.http.get<Matter[]>(this.api, { params });
  }

  // ─── Team ─────────────────────────────────────────────────────────
  people(): Observable<Person[]> {
    return this.http.get<Person[]>(`${this.api}/team/people`);
  }

  addTeamMember(matterId: string, payload: TeamMemberCreate): Observable<TeamMember> {
    return this.http.post<TeamMember>(`${this.api}/${matterId}/team`, payload);
  }

  updateTeamMember(matterId: string, memberId: string, payload: Partial<TeamMemberCreate>): Observable<TeamMember> {
    return this.http.patch<TeamMember>(`${this.api}/${matterId}/team/${memberId}`, payload);
  }

  /** End a stint and (optionally) start the successor's — returns both rows. */
  handover(matterId: string, memberId: string, payload: TeamHandover): Observable<TeamMember[]> {
    return this.http.post<TeamMember[]>(`${this.api}/${matterId}/team/${memberId}/handover`, payload);
  }

  removeTeamMember(matterId: string, memberId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${matterId}/team/${memberId}`);
  }

  /** Move every active stint of one person to another (they left, etc.). */
  transfer(payload: TeamTransfer): Observable<TeamTransferResult> {
    return this.http.post<TeamTransferResult>(`${this.api}/team/transfer`, payload);
  }

  // ─── Fees ─────────────────────────────────────────────────────────
  addFeeArrangement(matterId: string, payload: FeeArrangementCreate): Observable<FeeArrangement> {
    return this.http.post<FeeArrangement>(`${this.api}/${matterId}/fees`, payload);
  }

  updateFeeArrangement(matterId: string, id: string, payload: Partial<FeeArrangementCreate> & { effective_to?: string | null }): Observable<FeeArrangement> {
    return this.http.patch<FeeArrangement>(`${this.api}/${matterId}/fees/${id}`, payload);
  }

  removeFeeArrangement(matterId: string, id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${matterId}/fees/${id}`);
  }

  triggerMilestone(matterId: string, milestoneId: string): Observable<FeeEvent> {
    return this.http.post<FeeEvent>(`${this.api}/${matterId}/fees/milestones/${milestoneId}/trigger`, {});
  }

  waiveMilestone(matterId: string, milestoneId: string): Observable<Milestone> {
    return this.http.post<Milestone>(`${this.api}/${matterId}/fees/milestones/${milestoneId}/waive`, {});
  }

  feeSummary(matterId: string): Observable<FeeSummary> {
    return this.http.get<FeeSummary>(`${this.api}/${matterId}/fees/summary`);
  }

  addFeeEvent(matterId: string, payload: { description: string; amount: number; occurred_on?: string | null; due_days?: number }): Observable<FeeEvent> {
    return this.http.post<FeeEvent>(`${this.api}/${matterId}/fees/events`, payload);
  }

  setFeeEventStatus(matterId: string, eventId: string, status: FeeEventStatus): Observable<FeeEvent> {
    return this.http.post<FeeEvent>(`${this.api}/${matterId}/fees/events/${eventId}/status`, {}, { params: { status } });
  }

  get(id: string): Observable<MatterDetail> {
    return this.http.get<MatterDetail>(`${this.api}/${id}`);
  }

  create(payload: MatterCreate): Observable<MatterDetail> {
    return this.http.post<MatterDetail>(this.api, payload);
  }

  update(id: string, payload: MatterUpdate): Observable<MatterDetail> {
    return this.http.patch<MatterDetail>(`${this.api}/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${id}`);
  }

  upcomingHearings(): Observable<Hearing[]> {
    return this.http.get<Hearing[]>(`${this.api}/hearings/upcoming`);
  }

  timeline(id: string): Observable<TimelineEntry[]> {
    return this.http.get<TimelineEntry[]>(`${this.api}/${id}/timeline`);
  }

  // ── Sub-resources ─────────────────────────────────────────────
  // ─── eCourts ──────────────────────────────────────────────────────
  /** Read-only preview of a registry case; creates nothing. */
  ecourtsLookup(payload: ECourtsLookup): Observable<ECourtsCase> {
    return this.http.post<ECourtsCase>(`${this.api}/ecourts/lookup`, payload);
  }

  ecourtsImport(payload: ECourtsImport): Observable<MatterDetail> {
    return this.http.post<MatterDetail>(`${this.api}/ecourts/import`, payload);
  }

  /** Re-pull registry fields; leaves the firm's own data alone. */
  ecourtsRefresh(matterId: string): Observable<MatterDetail> {
    return this.http.post<MatterDetail>(`${this.api}/${matterId}/ecourts/refresh`, {});
  }

  // ─── Advocates ────────────────────────────────────────────────────
  addAdvocate(matterId: string, payload: AdvocateCreate): Observable<Advocate> {
    return this.http.post<Advocate>(`${this.api}/${matterId}/advocates`, payload);
  }

  removeAdvocate(matterId: string, advocateId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${matterId}/advocates/${advocateId}`);
  }

  /** Other matters where this counsel appeared against us. */
  opposingCounselHistory(name: string): Observable<Matter[]> {
    return this.http.get<Matter[]>(
      `${this.api}/advocates/opposing/${encodeURIComponent(name)}/history`,
    );
  }

  addParty(matterId: string, name: string, role: string, contact?: string): Observable<Party> {
    return this.http.post<Party>(`${this.api}/${matterId}/parties`, { name, role, contact });
  }

  addHearing(matterId: string, payload: Partial<Hearing> & { scheduled_on: string }): Observable<Hearing> {
    return this.http.post<Hearing>(`${this.api}/${matterId}/hearings`, payload);
  }

  updateHearing(hearingId: string, payload: Partial<Hearing>): Observable<Hearing> {
    return this.http.patch<Hearing>(`${this.api}/hearings/${hearingId}`, payload);
  }

  addTask(matterId: string, title: string, due_on?: string | null): Observable<Task> {
    return this.http.post<Task>(`${this.api}/${matterId}/tasks`, { title, due_on });
  }

  setTaskDone(taskId: string, done = true): Observable<Task> {
    return this.http.post<Task>(`${this.api}/tasks/${taskId}/done`, {}, { params: { done } });
  }

  addNote(matterId: string, body: string): Observable<Note> {
    return this.http.post<Note>(`${this.api}/${matterId}/notes`, { body });
  }

  addAuthority(matterId: string, payload: Omit<MatterAuthority, 'id' | 'matter_id' | 'created_by' | 'created_at'>): Observable<MatterAuthority> {
    return this.http.post<MatterAuthority>(`${this.api}/${matterId}/authorities`, payload);
  }

  removeAuthority(matterId: string, authorityId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${matterId}/authorities/${authorityId}`);
  }
}

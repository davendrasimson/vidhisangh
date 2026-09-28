import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { AdminAction, PlatformOverview, PlatformPost, PlatformTenant, PlatformUser, SupportTicket, TicketPriority, TicketStatus } from '@core/models/support.models';

@Injectable({ providedIn: 'root' })
export class SupportService {
  private readonly http = inject(HttpClient); private readonly api = environment.apiBaseUrl;
  create(payload: { subject: string; description: string; category: string; priority: TicketPriority; page_url: string; browser_context: string }): Observable<SupportTicket> { return this.http.post<SupportTicket>(`${this.api}/support/tickets`, payload); }
  mine(): Observable<SupportTicket[]> { return this.http.get<SupportTicket[]>(`${this.api}/support/tickets`); }
  reply(id: string, body: string): Observable<SupportTicket> { return this.http.post<SupportTicket>(`${this.api}/support/tickets/${id}/messages`, { body }); }
  adminMe(): Observable<{ allowed: boolean; email: string }> { return this.http.get<{ allowed: boolean; email: string }>(`${this.api}/platform-admin/me`); }
  overview(): Observable<PlatformOverview> { return this.http.get<PlatformOverview>(`${this.api}/platform-admin/overview`); }
  users(q = '', status = ''): Observable<PlatformUser[]> { const params: Record<string, string> = {}; if (q) params['q'] = q; if (status) params['status'] = status; return this.http.get<PlatformUser[]>(`${this.api}/platform-admin/users`, { params }); }
  user(id: string): Observable<PlatformUser> { return this.http.get<PlatformUser>(`${this.api}/platform-admin/users/${id}`); }
  setUserStatus(id: string, active: boolean, reason: string): Observable<PlatformUser> { return this.http.patch<PlatformUser>(`${this.api}/platform-admin/users/${id}/status`, { active, reason }); }
  restrictPosting(id: string, days: number | null, reason: string): Observable<PlatformUser> { return this.http.patch<PlatformUser>(`${this.api}/platform-admin/users/${id}/posting-restriction`, { days, reason }); }
  removeNetworkProfile(id: string, reason: string): Observable<void> { return this.http.post<void>(`${this.api}/platform-admin/users/${id}/remove-network-profile`, { reason }); }
  tenants(q = ''): Observable<PlatformTenant[]> { return this.http.get<PlatformTenant[]>(`${this.api}/platform-admin/tenants`, { params: q ? { q } : {} }); }
  setTenantStatus(id: string, status: string, reason: string): Observable<PlatformTenant> { return this.http.patch<PlatformTenant>(`${this.api}/platform-admin/tenants/${id}/status`, { status, reason }); }
  posts(q = '', includeRemoved = true): Observable<PlatformPost[]> { return this.http.get<PlatformPost[]>(`${this.api}/platform-admin/posts`, { params: { ...(q ? { q } : {}), include_removed: String(includeRemoved) } }); }
  moderatePost(id: string, restore: boolean, reason: string): Observable<PlatformPost> { return this.http.post<PlatformPost>(`${this.api}/platform-admin/posts/${id}/${restore ? 'restore' : 'remove'}`, { reason }); }
  tickets(status = ''): Observable<SupportTicket[]> { return this.http.get<SupportTicket[]>(`${this.api}/platform-admin/tickets`, { params: status ? { status } : {} }); }
  updateTicket(id: string, patch: { status?: TicketStatus; priority?: TicketPriority; assign_to_me?: boolean; response?: string }): Observable<SupportTicket> { return this.http.patch<SupportTicket>(`${this.api}/platform-admin/tickets/${id}`, patch); }
  actions(): Observable<AdminAction[]> { return this.http.get<AdminAction[]>(`${this.api}/platform-admin/actions`); }
}

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { Role, User } from '@core/models/auth.models';
import { AuditEvent } from '@core/models/audit.models';
import { SystemOverview } from '@core/models/system.models';
import { ApiKey, ApiKeyCreated } from '@core/models/api-key.models';

export interface UserCreated {
  user: User;
  temporary_password: string;
}

@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly http = inject(HttpClient);
  private readonly api = environment.apiBaseUrl;

  system(): Observable<SystemOverview> {
    return this.http.get<SystemOverview>(`${this.api}/admin/system`);
  }

  users(page = 1, size = 50): Observable<User[]> {
    return this.http.get<User[]>(`${this.api}/tenants/users`, { params: { page, size } });
  }

  roles(): Observable<Role[]> {
    return this.http.get<Role[]>(`${this.api}/tenants/roles`);
  }

  createUser(payload: {
    email: string;
    full_name: string;
    role_codes: string[];
  }): Observable<UserCreated> {
    return this.http.post<UserCreated>(`${this.api}/tenants/users`, payload);
  }

  setUserRoles(userId: string, roleCodes: string[]): Observable<User> {
    return this.http.put<User>(`${this.api}/tenants/users/${userId}/roles`, {
      role_codes: roleCodes,
    });
  }

  setUserActive(userId: string, active: boolean): Observable<User> {
    const verb = active ? 'activate' : 'deactivate';
    return this.http.post<User>(`${this.api}/tenants/users/${userId}/${verb}`, {});
  }

  audit(action?: string, page = 1, size = 50): Observable<AuditEvent[]> {
    const params: Record<string, string | number> = { page, size };
    if (action) params['action'] = action;
    return this.http.get<AuditEvent[]>(`${this.api}/admin/audit`, { params });
  }

  apiKeys(): Observable<ApiKey[]> {
    return this.http.get<ApiKey[]>(`${this.api}/api-keys`);
  }

  apiKeyScopes(): Observable<string[]> {
    return this.http.get<string[]>(`${this.api}/api-keys/scopes`);
  }

  createApiKey(payload: { name: string; scopes: string[] }): Observable<ApiKeyCreated> {
    return this.http.post<ApiKeyCreated>(`${this.api}/api-keys`, payload);
  }

  revokeApiKey(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/api-keys/${id}`);
  }
}

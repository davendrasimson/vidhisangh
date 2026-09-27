import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { FeatureFlag, ResolvedFlags } from '@core/models/feature-flag.models';

@Injectable({ providedIn: 'root' })
export class FeatureFlagService {
  private readonly http = inject(HttpClient);
  private readonly api = environment.apiBaseUrl;

  /** Admin: full catalog with tenant overrides. Requires `tenant:manage`. */
  list(): Observable<FeatureFlag[]> {
    return this.http.get<FeatureFlag[]>(`${this.api}/admin/feature-flags`);
  }

  set(key: string, enabled: boolean): Observable<FeatureFlag> {
    return this.http.put<FeatureFlag>(`${this.api}/admin/feature-flags/${key}`, { enabled });
  }

  /** Resolved on/off map for the current tenant (any authenticated user). */
  resolved(): Observable<ResolvedFlags> {
    return this.http.get<ResolvedFlags>(`${this.api}/feature-flags`);
  }
}

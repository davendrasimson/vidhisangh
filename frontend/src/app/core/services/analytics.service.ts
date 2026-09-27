import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { AnalyticsOverview } from '@core/models/analytics.models';

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/analytics`;

  overview(): Observable<AnalyticsOverview> {
    return this.http.get<AnalyticsOverview>(`${this.api}/overview`);
  }
}

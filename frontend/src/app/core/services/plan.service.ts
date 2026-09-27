import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { Plan, PlanTier, Subscription } from '@core/models/plan.models';

@Injectable({ providedIn: 'root' })
export class PlanService {
  private readonly http = inject(HttpClient);
  private readonly api = environment.apiBaseUrl;

  plans(): Observable<Plan[]> {
    return this.http.get<Plan[]>(`${this.api}/admin/plans`);
  }

  subscription(): Observable<Subscription> {
    return this.http.get<Subscription>(`${this.api}/admin/subscription`);
  }

  changePlan(tier: PlanTier): Observable<Subscription> {
    return this.http.put<Subscription>(`${this.api}/admin/subscription`, { tier });
  }
}

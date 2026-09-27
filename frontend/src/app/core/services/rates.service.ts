import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { CounselRate, RateBasis, RateCard } from '@core/models/matters.models';

/** Counsel rate cards: what each person charges, by basis, over time. */
@Injectable({ providedIn: 'root' })
export class RatesService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/rates`;

  cards(): Observable<RateCard[]> {
    return this.http.get<RateCard[]>(`${this.api}/cards`);
  }

  create(payload: { user_id: string; basis: RateBasis; amount: number; effective_from?: string | null; effective_to?: string | null; notes?: string | null }): Observable<CounselRate> {
    return this.http.post<CounselRate>(this.api, payload);
  }

  update(id: string, payload: { amount?: number; effective_from?: string; effective_to?: string | null; notes?: string | null }): Observable<CounselRate> {
    return this.http.patch<CounselRate>(`${this.api}/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${id}`);
  }
}

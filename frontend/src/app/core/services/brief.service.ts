import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { Brief, QuizAnswer } from '@core/models/brief.models';

@Injectable({ providedIn: 'root' })
export class BriefService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/brief`;

  /** The brief for a day (today when omitted). `from` = 'push' when opened from the morning message. */
  get(day?: string | null, from?: string | null): Observable<Brief> {
    const params: Record<string, string> = {};
    if (day) params['day'] = day;
    if (from) params['from'] = from;
    return this.http.get<Brief>(this.api, { params });
  }

  answer(quizId: string, chosen: number): Observable<QuizAnswer> {
    return this.http.post<QuizAnswer>(`${this.api}/quiz/${quizId}/answer`, { chosen });
  }
}

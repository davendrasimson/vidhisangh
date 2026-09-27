import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { AgendaItem, CalendarEvent, EventCreate } from '@core/models/calendar.models';

@Injectable({ providedIn: 'root' })
export class CalendarService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/calendar`;

  agenda(start: string, end: string): Observable<AgendaItem[]> {
    return this.http.get<AgendaItem[]>(`${this.api}/agenda`, { params: { start, end } });
  }

  events(start: string, end: string): Observable<CalendarEvent[]> {
    return this.http.get<CalendarEvent[]>(`${this.api}/events`, { params: { start, end } });
  }

  create(payload: EventCreate): Observable<CalendarEvent> {
    return this.http.post<CalendarEvent>(`${this.api}/events`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/events/${id}`);
  }
}

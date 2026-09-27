import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { Conversation, Message } from '@core/models/messaging.models';

@Injectable({ providedIn: 'root' })
export class MessagingService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/conversations`;

  list(): Observable<Conversation[]> {
    return this.http.get<Conversation[]>(this.api);
  }

  get(id: string): Observable<Conversation> {
    return this.http.get<Conversation>(`${this.api}/${id}`);
  }

  startDirect(userId: string): Observable<Conversation> {
    return this.http.post<Conversation>(`${this.api}/direct/${userId}`, {});
  }

  createGroup(title: string, participant_ids: string[]): Observable<Conversation> {
    return this.http.post<Conversation>(`${this.api}/group`, { title, participant_ids });
  }

  messages(id: string, page = 1, size = 50): Observable<Message[]> {
    return this.http.get<Message[]>(`${this.api}/${id}/messages`, { params: { page, size } });
  }

  send(id: string, body: string): Observable<Message> {
    return this.http.post<Message>(`${this.api}/${id}/messages`, { body });
  }

  markRead(id: string): Observable<void> {
    return this.http.post<void>(`${this.api}/${id}/read`, {});
  }

  leave(id: string): Observable<void> {
    return this.http.post<void>(`${this.api}/${id}/leave`, {});
  }
}

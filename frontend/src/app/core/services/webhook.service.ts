import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  EventType,
  Webhook,
  WebhookCreated,
  WebhookDelivery,
} from '@core/models/webhook.models';

@Injectable({ providedIn: 'root' })
export class WebhookService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/webhooks`;

  events(): Observable<EventType[]> {
    return this.http.get<EventType[]>(`${this.api}/events`);
  }

  list(): Observable<Webhook[]> {
    return this.http.get<Webhook[]>(this.api);
  }

  create(payload: {
    url: string;
    description: string | null;
    event_types: string[];
  }): Observable<WebhookCreated> {
    return this.http.post<WebhookCreated>(this.api, payload);
  }

  update(id: string, payload: Partial<Pick<Webhook, 'is_active' | 'event_types' | 'description'>>): Observable<Webhook> {
    return this.http.patch<Webhook>(`${this.api}/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${id}`);
  }

  test(id: string): Observable<WebhookDelivery> {
    return this.http.post<WebhookDelivery>(`${this.api}/${id}/test`, {});
  }

  deliveries(id: string): Observable<WebhookDelivery[]> {
    return this.http.get<WebhookDelivery[]>(`${this.api}/${id}/deliveries`);
  }
}

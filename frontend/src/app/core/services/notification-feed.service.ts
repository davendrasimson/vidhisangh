import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  AppNotification,
  ChannelPreference,
  NotificationChannel,
  NotificationDelivery,
  WhatsAppUpdates,
} from '@core/models/notification.models';

/** backend notifications/router.py DailyEmailPreference */
export interface DailyEmailPreference {
  enabled: boolean;
  email_verified: boolean;
  /** The default without a choice: on without the app, off with it. */
  has_app: boolean;
  chosen: boolean;
}

/** API client for the in-app notification centre (distinct from the toast
 *  `NotificationService`, which wraps MatSnackBar). */
@Injectable({ providedIn: 'root' })
export class NotificationFeedService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/notifications`;

  list(page = 1, size = 20): Observable<AppNotification[]> {
    return this.http.get<AppNotification[]>(this.api, { params: { page, size } });
  }

  unreadCount(): Observable<{ count: number }> {
    return this.http.get<{ count: number }>(`${this.api}/unread-count`);
  }

  markRead(id: string): Observable<void> {
    return this.http.post<void>(`${this.api}/${id}/read`, {});
  }

  markAllRead(): Observable<void> {
    return this.http.post<void>(`${this.api}/read-all`, {});
  }

  preferences(): Observable<ChannelPreference[]> {
    return this.http.get<ChannelPreference[]>(`${this.api}/preferences`);
  }

  updatePreference(
    channel: NotificationChannel,
    payload: { enabled: boolean; types: string[] },
  ): Observable<ChannelPreference> {
    return this.http.put<ChannelPreference>(`${this.api}/preferences/${channel}`, payload);
  }

  /** Product updates on WhatsApp: the member's choice (a consent ledger on the server). */
  whatsappUpdates(): Observable<WhatsAppUpdates> {
    return this.http.get<WhatsAppUpdates>(`${this.api}/whatsapp-updates`);
  }

  setWhatsappUpdates(granted: boolean, source: 'settings' | 'home'): Observable<WhatsAppUpdates> {
    return this.http.put<WhatsAppUpdates>(`${this.api}/whatsapp-updates`, { granted, source });
  }

  /** VidhiSangh Daily on WhatsApp every morning: a separate choice from product updates. */
  whatsappDaily(): Observable<WhatsAppUpdates> {
    return this.http.get<WhatsAppUpdates>(`${this.api}/whatsapp-daily`);
  }

  setWhatsappDaily(granted: boolean, source: 'settings' | 'daily'): Observable<WhatsAppUpdates> {
    return this.http.put<WhatsAppUpdates>(`${this.api}/whatsapp-daily`, { granted, source });
  }

  /** VidhiSangh Daily by email (default on for members without the app). */
  dailyEmail(): Observable<DailyEmailPreference> {
    return this.http.get<DailyEmailPreference>(`${this.api}/daily-email`);
  }

  setDailyEmail(enabled: boolean): Observable<DailyEmailPreference> {
    return this.http.put<DailyEmailPreference>(`${this.api}/daily-email`, { enabled });
  }

  dailyOrders(): Observable<{ enabled: boolean; email_verified: boolean }> {
    return this.http.get<{ enabled: boolean; email_verified: boolean }>(`${this.api}/daily-orders`);
  }

  setDailyOrders(enabled: boolean): Observable<{ enabled: boolean; email_verified: boolean }> {
    return this.http.put<{ enabled: boolean; email_verified: boolean }>(`${this.api}/daily-orders`, { enabled });
  }

  deliveries(page = 1, size = 20): Observable<NotificationDelivery[]> {
    return this.http.get<NotificationDelivery[]>(`${this.api}/deliveries`, {
      params: { page, size },
    });
  }
}

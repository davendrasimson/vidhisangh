/** In-app notification contracts (mirrors the backend notifications module). */

export type NotificationType =
  | 'mention'
  | 'connection_request'
  | 'connection_accepted'
  | 'group_invite'
  | 'endorsement'
  | 'recommendation';

export interface AppNotification {
  id: string;
  type: NotificationType;
  actor_id: string | null;
  actor_name: string | null;
  message: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

export type NotificationChannel =
  | 'in_app'
  | 'email'
  | 'slack'
  | 'sms'
  | 'whatsapp'
  | 'push'
  | 'teams';

export type DeliveryStatus = 'sent' | 'failed' | 'skipped';

export interface ChannelPreference {
  channel: NotificationChannel;
  enabled: boolean;
  types: string[];
}

export interface NotificationDelivery {
  id: string;
  type: NotificationType;
  channel: NotificationChannel;
  status: DeliveryStatus;
  detail: string | null;
  created_at: string;
}

/** Product updates on WhatsApp (GET/PUT /notifications/whatsapp-updates). */
export interface WhatsAppUpdates {
  status: 'granted' | 'refused' | 'unasked';
  phone_verified: boolean;
}

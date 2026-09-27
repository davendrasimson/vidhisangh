/** Calendar API contracts (mirrors the backend calendar module). */

export type EventType = 'meeting' | 'court' | 'appointment' | 'reminder' | 'other';

export interface CalendarEvent {
  id: string;
  title: string;
  description: string | null;
  event_type: EventType;
  start_at: string;
  end_at: string | null;
  all_day: boolean;
  location: string | null;
  matter_id: string | null;
  assigned_to: string | null;
  created_at: string;
}

export interface EventCreate {
  title: string;
  description?: string | null;
  event_type?: EventType;
  start_at: string;
  end_at?: string | null;
  all_day?: boolean;
  location?: string | null;
  matter_id?: string | null;
}

export interface AgendaItem {
  kind: 'event' | 'hearing' | 'deadline' | 'limitation';
  id: string;
  title: string;
  start_at: string;
  end_at: string | null;
  all_day: boolean;
  event_type: string | null;
  status: string | null;
  location: string | null;
  matter_id: string | null;
  matter_number: string | null;
}

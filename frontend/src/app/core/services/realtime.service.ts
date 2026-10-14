import { HttpClient, HttpContext } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Subject, firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { TokenService } from '@core/auth/token.service';
import { Message } from '@core/models/messaging.models';
import { SILENT_ERRORS } from '@core/interceptors/error.interceptor';

export type RealtimeEvent =
  | { type: 'message'; conversation_id: string; message: Message }
  | { type: 'presence'; user_id: string; online: boolean }
  | { type: 'presence_snapshot'; online: string[] }
  | { type: 'typing'; conversation_id: string; user_id: string };

interface WsTicket {
  ticket: string;
  expires_in: number;
}

/** Retry delay after `attempt` failures: 3 s, doubling, at most 60 s. */
export function reconnectDelay(attempt: number): number {
  return Math.min(3000 * 2 ** Math.max(attempt, 0), 60_000);
}

/** Live messaging socket: delivers messages, presence and typing signals.
 *  Single connection, auto-reconnecting while authenticated.
 *
 *  Reconnecting is a background job, so it never shows an error. It pauses
 *  while the page is hidden or the device is offline (a phone in the
 *  background has no network: retrying every 3 s there used to pile up
 *  "Cannot reach the server" toasts), backs off up to a minute, and
 *  reconnects at once when the page is visible and online again.
 *
 *  The handshake carries a 60-second single-use ticket from
 *  `POST /auth/ws-ticket`, never the access token itself (audit A-26: the
 *  query string ends up in access logs). */
@Injectable({ providedIn: 'root' })
export class RealtimeService {
  private readonly tokens = inject(TokenService);
  private readonly http = inject(HttpClient);
  private readonly api = environment.apiBaseUrl;

  private socket: WebSocket | null = null;
  private connecting = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUs = false;
  private failures = 0;

  constructor() {
    if (typeof document === 'undefined') return;
    const resume = () => {
      if (this.closedByUs || document.visibilityState !== 'visible' || !navigator.onLine) return;
      this.failures = 0;
      this.connect();
    };
    document.addEventListener('visibilitychange', resume);
    window.addEventListener('online', resume);
  }

  /** Events other than presence (message, typing) for components to consume. */
  readonly events = new Subject<RealtimeEvent>();

  private readonly _online = signal<ReadonlySet<string>>(new Set());
  readonly online = computed(() => this._online());

  connect(): void {
    if (this.connecting || (this.socket && this.socket.readyState <= WebSocket.OPEN)) return;
    if (!this.tokens.accessToken()) return;
    this.closedByUs = false;
    this.connecting = true;
    void this.openWithTicket().finally(() => (this.connecting = false));
  }

  private async openWithTicket(): Promise<void> {
    let ticket: string;
    try {
      ({ ticket } = await firstValueFrom(this.http.post<WsTicket>(`${this.api}/auth/ws-ticket`, {}, {
        context: new HttpContext().set(SILENT_ERRORS, true),
      })));
    } catch {
      // Not signed in (or the API is down): try again later unless we were told to stop.
      if (!this.closedByUs) this.scheduleReconnect();
      return;
    }
    if (this.closedByUs) return;

    const base = this.wsBase();
    const socket = new WebSocket(`${base}/ws?ticket=${encodeURIComponent(ticket)}`);
    this.socket = socket;

    socket.onopen = () => (this.failures = 0);
    socket.onmessage = (e) => this.handle(JSON.parse(e.data) as RealtimeEvent);
    socket.onclose = () => {
      this.socket = null;
      this._online.set(new Set());
      if (!this.closedByUs) this.scheduleReconnect();
    };
    socket.onerror = () => socket.close();
  }

  /** `apiBaseUrl` may be relative in production (`/api/v1`): resolve against the page. */
  private wsBase(): string {
    const absolute = new URL(this.api, window.location.origin).toString().replace(/\/$/, '');
    return absolute.replace(/^http/, 'ws');
  }

  disconnect(): void {
    this.closedByUs = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = null;
  }

  isOnline(userId: string): boolean {
    return this._online().has(userId);
  }

  sendTyping(conversationId: string): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: 'typing', conversation_id: conversationId }));
    }
  }

  private handle(event: RealtimeEvent): void {
    switch (event.type) {
      case 'presence_snapshot':
        this._online.set(new Set(event.online));
        break;
      case 'presence':
        this._online.update((set) => {
          const next = new Set(set);
          if (event.online) next.add(event.user_id);
          else next.delete(event.user_id);
          return next;
        });
        break;
      default:
        this.events.next(event);
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    // Hidden or offline: wait for the visibilitychange / online event instead.
    if (typeof document === 'undefined' || document.visibilityState !== 'visible' || !navigator.onLine) return;
    this.reconnectTimer = setTimeout(() => this.connect(), reconnectDelay(this.failures++));
  }
}

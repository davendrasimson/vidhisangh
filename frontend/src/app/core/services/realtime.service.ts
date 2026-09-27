import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Subject, firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { TokenService } from '@core/auth/token.service';
import { Message } from '@core/models/messaging.models';

export type RealtimeEvent =
  | { type: 'message'; conversation_id: string; message: Message }
  | { type: 'presence'; user_id: string; online: boolean }
  | { type: 'presence_snapshot'; online: string[] }
  | { type: 'typing'; conversation_id: string; user_id: string };

interface WsTicket {
  ticket: string;
  expires_in: number;
}

/** Live messaging socket: delivers messages, presence and typing signals.
 *  Single connection, auto-reconnecting while authenticated.
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
      ({ ticket } = await firstValueFrom(this.http.post<WsTicket>(`${this.api}/auth/ws-ticket`, {})));
    } catch {
      // Not signed in (or the API is down): try again later unless we were told to stop.
      if (!this.closedByUs) this.scheduleReconnect();
      return;
    }
    if (this.closedByUs) return;

    const base = this.wsBase();
    const socket = new WebSocket(`${base}/ws?ticket=${encodeURIComponent(ticket)}`);
    this.socket = socket;

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
    this.reconnectTimer = setTimeout(() => this.connect(), 3000);
  }
}

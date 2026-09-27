import { Injectable, computed, inject, signal } from '@angular/core';
import { Subject } from 'rxjs';
import { environment } from '@env/environment';
import { TokenService } from '@core/auth/token.service';
import { Message } from '@core/models/messaging.models';

export type RealtimeEvent =
  | { type: 'message'; conversation_id: string; message: Message }
  | { type: 'presence'; user_id: string; online: boolean }
  | { type: 'presence_snapshot'; online: string[] }
  | { type: 'typing'; conversation_id: string; user_id: string };

/** Live messaging socket: delivers messages, presence and typing signals.
 *  Single connection, auto-reconnecting while authenticated. */
@Injectable({ providedIn: 'root' })
export class RealtimeService {
  private readonly tokens = inject(TokenService);

  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUs = false;

  /** Events other than presence (message, typing) for components to consume. */
  readonly events = new Subject<RealtimeEvent>();

  private readonly _online = signal<ReadonlySet<string>>(new Set());
  readonly online = computed(() => this._online());

  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return;
    const token = this.tokens.accessToken();
    if (!token) return;

    this.closedByUs = false;
    const base = environment.apiBaseUrl.replace(/^http/, 'ws');
    const socket = new WebSocket(`${base}/ws?token=${encodeURIComponent(token)}`);
    this.socket = socket;

    socket.onmessage = (e) => this.handle(JSON.parse(e.data) as RealtimeEvent);
    socket.onclose = () => {
      this.socket = null;
      this._online.set(new Set());
      if (!this.closedByUs) this.scheduleReconnect();
    };
    socket.onerror = () => socket.close();
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

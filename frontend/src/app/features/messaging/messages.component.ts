import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '@core/auth/auth.service';
import { MessagingService } from '@core/services/messaging.service';
import { NetworkService } from '@core/services/network.service';
import { NotificationService } from '@core/services/notification.service';
import { RealtimeService, RealtimeEvent } from '@core/services/realtime.service';
import { Conversation, Message } from '@core/models/messaging.models';
import { DirectoryPerson } from '@core/models/network.models';

@Component({
  selector: 'app-messages',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, MatIconModule, MatButtonModule],
  templateUrl: './messages.component.html',
})
export class MessagesComponent implements OnInit, OnDestroy {
  private readonly svc = inject(MessagingService);
  private readonly net = inject(NetworkService);
  private readonly notify = inject(NotificationService);
  private readonly auth = inject(AuthService);
  protected readonly realtime = inject(RealtimeService);

  protected readonly conversations = signal<Conversation[]>([]);
  protected readonly active = signal<Conversation | null>(null);
  protected readonly messages = signal<Message[]>([]);
  protected readonly draft = signal('');
  protected readonly loading = signal(true);
  protected readonly sending = signal(false);
  protected readonly typingIn = signal<string | null>(null);

  // New-chat directory picker.
  protected readonly showNewChat = signal(false);
  protected readonly directory = signal<DirectoryPerson[]>([]);

  private lastTypingSent = 0;
  private typingTimer: ReturnType<typeof setTimeout> | null = null;

  protected readonly myId = computed(() => this.auth.user()?.id ?? '');

  constructor() {
    this.realtime.events.pipe(takeUntilDestroyed()).subscribe((e) => this.onRealtime(e));
  }

  async ngOnInit(): Promise<void> {
    this.realtime.connect();
    await this.loadConversations();
  }

  ngOnDestroy(): void {
    if (this.typingTimer) clearTimeout(this.typingTimer);
  }

  private onRealtime(event: RealtimeEvent): void {
    if (event.type === 'message') {
      const active = this.active();
      if (active && event.conversation_id === active.id) {
        // Append live (dedupe) and keep the thread marked read.
        this.messages.update((list) =>
          list.some((m) => m.id === event.message.id) ? list : [...list, event.message],
        );
        void firstValueFrom(this.svc.markRead(active.id));
      } else {
        this.patchConversation(event.conversation_id, { unread_count: this.unreadOf(event.conversation_id) + 1 });
      }
      this.patchConversation(event.conversation_id, {
        last_message_preview: event.message.body.slice(0, 200),
        last_message_at: event.message.created_at,
      });
      this.bumpToTop(event.conversation_id);
    } else if (event.type === 'typing') {
      const active = this.active();
      if (active && event.conversation_id === active.id && event.user_id !== this.myId()) {
        this.typingIn.set(active.id);
        if (this.typingTimer) clearTimeout(this.typingTimer);
        this.typingTimer = setTimeout(() => this.typingIn.set(null), 3000);
      }
    }
  }

  private unreadOf(id: string): number {
    return this.conversations().find((c) => c.id === id)?.unread_count ?? 0;
  }

  private async loadConversations(): Promise<void> {
    this.loading.set(true);
    try {
      this.conversations.set(await firstValueFrom(this.svc.list()));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected title(c: Conversation): string {
    if (c.type === 'group') return c.title || 'Group chat';
    const other = c.participants.find((p) => p.user_id !== this.myId());
    return other?.participant_name ?? 'Conversation';
  }

  protected otherOnline(c: Conversation): boolean {
    if (c.type !== 'direct') return false;
    const other = c.participants.find((p) => p.user_id !== this.myId());
    return other ? this.realtime.isOnline(other.user_id) : false;
  }

  protected onType(value: string): void {
    this.draft.set(value);
    const active = this.active();
    const now = Date.now();
    if (active && value && now - this.lastTypingSent > 1500) {
      this.lastTypingSent = now;
      this.realtime.sendTyping(active.id);
    }
  }

  protected initials(name: string): string {
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || '?';
  }

  protected async select(c: Conversation): Promise<void> {
    this.active.set(c);
    this.messages.set([]);
    this.typingIn.set(null);
    try {
      this.messages.set(await firstValueFrom(this.svc.messages(c.id)));
      // Opening marks it read server-side; reflect locally.
      this.patchConversation(c.id, { unread_count: 0 });
    } catch {
      /* handled */
    }
  }

  protected async send(): Promise<void> {
    const c = this.active();
    const body = this.draft().trim();
    if (!c || !body || this.sending()) return;
    this.sending.set(true);
    try {
      const message = await firstValueFrom(this.svc.send(c.id, body));
      this.messages.update((list) => [...list, message]);
      this.draft.set('');
      this.patchConversation(c.id, {
        last_message_preview: body.slice(0, 200),
        last_message_at: message.created_at,
      });
      this.bumpToTop(c.id);
    } catch {
      /* handled */
    } finally {
      this.sending.set(false);
    }
  }

  // ── New chat ───────────────────────────────────────────────────
  protected async toggleNewChat(): Promise<void> {
    const next = !this.showNewChat();
    this.showNewChat.set(next);
    if (next && this.directory().length === 0) {
      try {
        this.directory.set(await firstValueFrom(this.net.directory()));
      } catch {
        /* handled */
      }
    }
  }

  protected async startChat(person: DirectoryPerson): Promise<void> {
    this.showNewChat.set(false);
    try {
      const conv = await firstValueFrom(this.svc.startDirect(person.user_id));
      const existing = this.conversations().find((c) => c.id === conv.id);
      if (!existing) this.conversations.update((list) => [conv, ...list]);
      await this.select(existing ?? conv);
    } catch {
      /* handled */
    }
  }

  private patchConversation(id: string, changes: Partial<Conversation>): void {
    this.conversations.update((list) =>
      list.map((c) => (c.id === id ? { ...c, ...changes } : c)),
    );
    const a = this.active();
    if (a && a.id === id) this.active.set({ ...a, ...changes });
  }

  private bumpToTop(id: string): void {
    this.conversations.update((list) => {
      const found = list.find((c) => c.id === id);
      return found ? [found, ...list.filter((c) => c.id !== id)] : list;
    });
  }
}

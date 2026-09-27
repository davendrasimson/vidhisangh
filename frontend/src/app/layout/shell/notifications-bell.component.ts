import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatBadgeModule } from '@angular/material/badge';
import { MatTooltipModule } from '@angular/material/tooltip';
import { NotificationFeedService } from '@core/services/notification-feed.service';
import { AppNotification } from '@core/models/notification.models';

@Component({
  selector: 'app-notifications-bell',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe, MatIconModule, MatButtonModule, MatMenuModule, MatBadgeModule, MatTooltipModule,
  ],
  template: `
    <button mat-icon-button matTooltip="Notifications" aria-label="Notifications"
            [matMenuTriggerFor]="menu" (menuOpened)="loadList()"
            [matBadge]="unread()" [matBadgeHidden]="unread() === 0" matBadgeColor="warn" matBadgeSize="small">
      <mat-icon class="material-icons-outlined">notifications</mat-icon>
    </button>

    <mat-menu #menu="matMenu" class="vs-notif-menu">
      <div class="flex items-center justify-between px-4 py-2 border-b border-line" (click)="$event.stopPropagation()">
        <span class="font-semibold">Notifications</span>
        @if (unread()) {
          <button mat-button (click)="markAll()">Mark all read</button>
        }
      </div>
      @if (items().length === 0) {
        <p class="text-content-muted text-sm px-4 py-6 text-center">You're all caught up.</p>
      } @else {
        @for (n of items(); track n.id) {
          <button mat-menu-item (click)="open(n)" [class.vs-notif--unread]="!n.is_read">
            <div class="flex flex-col items-start py-1 max-w-xs">
              <span class="whitespace-normal text-sm leading-snug">{{ n.message }}</span>
              <span class="text-xs text-content-muted">{{ n.created_at | date: 'MMM d, h:mm a' }}</span>
            </div>
          </button>
        }
      }
      <button mat-menu-item class="border-t border-line" (click)="openSettings()">
        <mat-icon class="material-icons-outlined">tune</mat-icon>
        <span>Notification settings</span>
      </button>
    </mat-menu>
  `,
})
export class NotificationsBellComponent implements OnInit {
  private readonly feed = inject(NotificationFeedService);
  private readonly router = inject(Router);

  protected readonly unread = signal(0);
  protected readonly items = signal<AppNotification[]>([]);

  async ngOnInit(): Promise<void> {
    await this.refreshCount();
  }

  private async refreshCount(): Promise<void> {
    try {
      this.unread.set((await firstValueFrom(this.feed.unreadCount())).count);
    } catch {
      /* handled */
    }
  }

  protected async loadList(): Promise<void> {
    try {
      this.items.set(await firstValueFrom(this.feed.list()));
    } catch {
      /* handled */
    }
  }

  protected async open(n: AppNotification): Promise<void> {
    if (!n.is_read) {
      try {
        await firstValueFrom(this.feed.markRead(n.id));
        this.items.update((list) => list.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
        this.unread.update((c) => Math.max(0, c - 1));
      } catch {
        /* handled */
      }
    }
    if (n.link) await this.router.navigateByUrl(n.link);
  }

  protected async markAll(): Promise<void> {
    try {
      await firstValueFrom(this.feed.markAllRead());
      this.items.update((list) => list.map((x) => ({ ...x, is_read: true })));
      this.unread.set(0);
    } catch {
      /* handled */
    }
  }

  protected openSettings(): void {
    void this.router.navigateByUrl('/app/settings/notifications');
  }
}

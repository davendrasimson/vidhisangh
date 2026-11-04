import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { NotificationFeedService } from '@core/services/notification-feed.service';
import { WhatsappRemindersComponent } from '@shared/whatsapp-reminders/whatsapp-reminders.component';
import { WhatsappUpdatesComponent } from '@shared/whatsapp-updates/whatsapp-updates.component';
import { WhatsappDailyComponent } from '@shared/whatsapp-daily/whatsapp-daily.component';
import { NotificationService } from '@core/services/notification.service';
import {
  ChannelPreference,
  NotificationChannel,
  NotificationDelivery,
} from '@core/models/notification.models';

interface ChannelMeta {
  channel: NotificationChannel;
  label: string;
  icon: string;
  hint: string;
  live: boolean; // has a working provider today
}

@Component({
  selector: 'app-notification-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatIconModule, MatSlideToggleModule, WhatsappRemindersComponent, WhatsappUpdatesComponent, WhatsappDailyComponent],
  templateUrl: './notification-settings.component.html',
})
export class NotificationSettingsComponent implements OnInit {
  private readonly feed = inject(NotificationFeedService);
  private readonly notify = inject(NotificationService);

  protected readonly prefs = signal<Record<NotificationChannel, ChannelPreference | undefined>>(
    {} as Record<NotificationChannel, ChannelPreference | undefined>,
  );
  protected readonly deliveries = signal<NotificationDelivery[]>([]);
  protected readonly loading = signal(true);
  protected readonly saving = signal<NotificationChannel | null>(null);
  protected readonly dailyOrders = signal({ enabled: false, email_verified: false });
  protected readonly savingDailyOrders = signal(false);
  protected readonly dailyOrdersAvailable = signal(false);

  protected readonly channels: ChannelMeta[] = [
    { channel: 'in_app', label: 'In-app', icon: 'notifications', hint: 'Always on — the bell in your header.', live: true },
    { channel: 'email', label: 'Email', icon: 'mail', hint: 'Delivered to your account email.', live: true },
    { channel: 'slack', label: 'Slack', icon: 'tag', hint: 'Posts to your firm’s Slack webhook.', live: true },
    { channel: 'sms', label: 'SMS', icon: 'sms', hint: 'Coming soon — awaits an SMS gateway.', live: false },
    { channel: 'push', label: 'Push (mobile app)', icon: 'notifications_active', hint: 'On your phone when the VidhiSangh app is allowed to send notifications.', live: true },
    { channel: 'teams', label: 'Microsoft Teams', icon: 'groups', hint: 'Coming soon — Teams connector.', live: false },
  ];

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadPrefs(), this.loadDeliveries(), this.loadDailyOrders()]);
    this.loading.set(false);
  }

  private async loadDailyOrders(): Promise<void> {
    try {
      this.dailyOrders.set(await firstValueFrom(this.feed.dailyOrders()));
      this.dailyOrdersAvailable.set(true);
    } catch {
      this.dailyOrdersAvailable.set(false);
    }
  }

  protected async toggleDailyOrders(enabled: boolean): Promise<void> {
    this.savingDailyOrders.set(true);
    try {
      this.dailyOrders.set(await firstValueFrom(this.feed.setDailyOrders(enabled)));
      this.notify.success(enabled ? 'Subscribed to Supreme Court order emails.' : 'Supreme Court order emails stopped.');
    } catch {
      await this.loadDailyOrders();
    } finally {
      this.savingDailyOrders.set(false);
    }
  }

  private async loadPrefs(): Promise<void> {
    const list = await firstValueFrom(this.feed.preferences());
    const map = {} as Record<NotificationChannel, ChannelPreference | undefined>;
    for (const p of list) map[p.channel] = p;
    this.prefs.set(map);
  }

  private async loadDeliveries(): Promise<void> {
    this.deliveries.set(await firstValueFrom(this.feed.deliveries()));
  }

  protected enabled(channel: NotificationChannel): boolean {
    // Push is on unless switched off: the phone's own permission prompt is the opt-in.
    return this.prefs()[channel]?.enabled ?? channel === 'push';
  }

  protected async toggle(meta: ChannelMeta, value: boolean): Promise<void> {
    if (meta.channel === 'in_app') return; // locked on
    this.saving.set(meta.channel);
    const current = this.prefs()[meta.channel];
    try {
      const updated = await firstValueFrom(
        this.feed.updatePreference(meta.channel, { enabled: value, types: current?.types ?? [] }),
      );
      this.prefs.update((m) => ({ ...m, [meta.channel]: updated }));
      this.notify.success(`${meta.label} notifications ${value ? 'enabled' : 'disabled'}.`);
      if (!meta.live && value) {
        this.notify.info(`${meta.label} has no provider yet — messages will be logged as “skipped”.`);
      }
    } catch {
      /* handled by interceptor; revert visual state on next load */
      await this.loadPrefs();
    } finally {
      this.saving.set(null);
    }
  }

  protected label(s: string): string {
    return s.replace(/_/g, ' ');
  }
}

import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { WhatsAppUpdates } from '@core/models/notification.models';
import { NotificationFeedService } from '@core/services/notification-feed.service';
import { NotificationService } from '@core/services/notification.service';
import { WHATSAPP_NUMBER } from '@core/contact';

/**
 * Product updates on WhatsApp: the member's consent (25 Oct 2026). Separate
 * from hearing reminders. Every yes or no is recorded on the server with the
 * date and the privacy-notice version; a no is always respected.
 *
 *   <vs-whatsapp-updates />          switch (Settings → Notifications)
 *   <vs-whatsapp-updates prompt />   one-time question on Home: shown only
 *                                    while never answered and the number is verified
 */
@Component({
  selector: 'vs-whatsapp-updates',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatButtonModule, MatIconModule, MatSlideToggleModule],
  template: `
    @if (visible()) {
      <section class="rounded-card border p-4 grid gap-3" [class]="prompt() ? 'border-brand/40 bg-brand/5' : 'border-line bg-surface-raised shadow-card'" aria-labelledby="wa-updates-title">
        <div class="flex items-start gap-3">
          <mat-icon class="material-icons-outlined text-success shrink-0">campaign</mat-icon>
          <div class="flex-1 min-w-0">
            <h2 id="wa-updates-title" class="font-semibold text-content">{{ prompt() ? 'Get product updates on WhatsApp?' : 'Product updates on WhatsApp' }}</h2>
            <p class="text-sm text-content-muted">About once or twice a month, VidhiSangh ({{ number }}) tells you about new features. Separate from hearing reminders; switch off any time in Settings → Notifications. See the <a routerLink="/privacy" class="text-brand">privacy notice</a>.</p>
          </div>
          @if (!prompt() && state()?.phone_verified) {
            <mat-slide-toggle [checked]="state()?.status === 'granted'" [disabled]="busy()" (change)="answer($event.checked)" aria-label="Product updates on WhatsApp" />
          }
        </div>
        @if (prompt()) {
          <div class="flex flex-wrap gap-2">
            <button mat-flat-button color="primary" [disabled]="busy()" (click)="answer(true)">Yes, send updates</button>
            <button mat-button [disabled]="busy()" (click)="answer(false)">No thanks</button>
          </div>
        } @else if (!state()?.phone_verified) {
          <p class="text-xs text-content-muted">Add and verify your mobile number in the hearing-reminders card above to receive these.</p>
        } @else {
          <p class="text-xs text-content-muted">{{ state()?.status === 'granted' ? 'On' : 'Off' }}</p>
        }
      </section>
    }
  `,
})
export class WhatsappUpdatesComponent implements OnInit {
  private readonly feed = inject(NotificationFeedService);
  private readonly notify = inject(NotificationService);

  readonly prompt = input(false, { transform: (v: boolean | string) => v !== false });
  protected readonly number = WHATSAPP_NUMBER;
  protected readonly state = signal<WhatsAppUpdates | null>(null);
  protected readonly busy = signal(false);
  protected readonly visible = computed(() => {
    const s = this.state();
    if (!s) return false;
    return this.prompt() ? s.status === 'unasked' && s.phone_verified : true;
  });

  async ngOnInit(): Promise<void> {
    try { this.state.set(await firstValueFrom(this.feed.whatsappUpdates())); } catch { /* card stays hidden */ }
  }

  protected async answer(granted: boolean): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    try {
      this.state.set(await firstValueFrom(this.feed.setWhatsappUpdates(granted, this.prompt() ? 'home' : 'settings')));
      this.notify.success(granted ? 'You will get product updates on WhatsApp.' : 'No product updates on WhatsApp. You can change this in Settings → Notifications.');
    } catch { /* interceptor shows the error */ } finally { this.busy.set(false); }
  }
}

import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { AuthService } from '@core/auth/auth.service';
import { problemMessage } from '@core/http/problem-message';
import { NotificationFeedService } from '@core/services/notification-feed.service';
import { NotificationService } from '@core/services/notification.service';
import { VsPhoneInputComponent } from '@shared/phone-input/vs-phone-input.component';
import { SendCodeCooldown } from '../../features/auth/send-code-cooldown';

const DISMISS_KEY = 'vs_wa_reminders_prompt_dismissed';

/**
 * WhatsApp hearing reminders: every evening a message from VidhiSangh's
 * number lists tomorrow's hearings. Turning it on asks for (and verifies)
 * a mobile number first if the account has none.
 *
 *   <vs-whatsapp-reminders />          full card (Settings → Notifications)
 *   <vs-whatsapp-reminders prompt />   only while off; can be dismissed (diary)
 */
@Component({
  selector: 'vs-whatsapp-reminders',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatButtonModule, MatIconModule, MatSlideToggleModule, VsPhoneInputComponent],
  template: `
    @if (visible()) {
      <section class="rounded-card border p-4 grid gap-3" [class]="prompt() ? 'border-brand/40 bg-brand/5' : 'border-line bg-surface-raised shadow-card'">
        <div class="flex items-start gap-3">
          <mat-icon class="material-icons-outlined text-success shrink-0">chat</mat-icon>
          <div class="flex-1 min-w-0">
            <h2 class="font-semibold text-content">WhatsApp reminders of tomorrow's hearings</h2>
            <p class="text-sm text-content-muted">Every evening at about 7 pm, VidhiSangh (+91 73411 00692) sends you one WhatsApp message listing your next day's hearings.</p>
          </div>
          @if (verified()) {
            <mat-slide-toggle [checked]="enabled()" [disabled]="busy()" (change)="setEnabled($event.checked)" aria-label="WhatsApp hearing reminders" />
          }
          @if (prompt()) {
            <button mat-icon-button type="button" (click)="dismiss()" aria-label="Not now"><mat-icon>close</mat-icon></button>
          }
        </div>
        @if (error()) { <p role="alert" class="text-sm text-danger">{{ error() }}</p> }
        @if (verified()) {
          <p class="text-xs text-content-muted">
            {{ enabled() ? 'On' : 'Off' }} · sent to {{ phone() }}. Only hearings on matters where you are counsel or on the team are listed.
          </p>
        } @else {
          <form class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start" (ngSubmit)="challenge() ? verify() : send()">
            @if (!challenge()) {
              <vs-phone-input name="phone" [(ngModel)]="number" #phoneField="ngModel" required />
              <button mat-flat-button type="submit" class="h-11" [disabled]="busy() || !number || !!phoneField.invalid || !!cooldown.seconds()">
                {{ cooldown.seconds() ? 'Wait ' + cooldown.seconds() + 's' : 'Send WhatsApp code' }}
              </button>
            } @else {
              <input class="vs-input" name="code" [(ngModel)]="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="6-digit code from WhatsApp" aria-label="WhatsApp code" />
              <button mat-flat-button type="submit" class="h-11" [disabled]="busy() || code.length !== 6">Verify and turn on</button>
              <button mat-button type="button" class="sm:col-span-2 justify-self-start" (click)="challenge.set(null)">Use a different number</button>
            }
            <p class="text-xs text-content-muted sm:col-span-2">Add your mobile number to turn this on. We send a code on WhatsApp to confirm it.</p>
          </form>
        }
      </section>
    }
  `,
})
export class WhatsappRemindersComponent implements OnInit {
  /** Diary prompt: shown only while reminders are off, and can be dismissed. */
  readonly prompt = input(false, { transform: (v: unknown) => v !== false && v !== 'false' });

  private readonly auth = inject(AuthService);
  private readonly feed = inject(NotificationFeedService);
  private readonly notify = inject(NotificationService);

  protected readonly enabled = signal(false);
  protected readonly loaded = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly challenge = signal<string | null>(null);
  protected readonly dismissed = signal(readDismissed());
  protected readonly cooldown = new SendCodeCooldown();
  protected number = '';
  protected code = '';

  protected readonly verified = computed(() => !!this.auth.user()?.is_phone_verified && !!this.auth.user()?.phone);
  protected readonly phone = computed(() => this.auth.user()?.phone ?? '');
  protected readonly visible = computed(() => this.loaded() && (!this.prompt() || (!this.enabled() && !this.dismissed())));

  async ngOnInit(): Promise<void> {
    try {
      const prefs = await firstValueFrom(this.feed.preferences());
      this.enabled.set(prefs.some((p) => p.channel === 'whatsapp' && p.enabled));
    } catch { /* toast shown */ }
    this.loaded.set(true);
  }

  protected async setEnabled(on: boolean): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const p = await firstValueFrom(this.feed.updatePreference('whatsapp', { enabled: on, types: [] }));
      this.enabled.set(p.enabled);
      this.notify.success(on ? 'WhatsApp hearing reminders are on.' : 'WhatsApp hearing reminders are off.');
    } catch (err) {
      this.error.set(problemMessage(err, 'Could not save. Please try again.'));
    } finally { this.busy.set(false); }
  }

  protected async send(): Promise<void> {
    if (this.busy() || this.cooldown.seconds()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const r = await firstValueFrom(this.auth.requestMyPhoneCode(this.number));
      this.challenge.set(r.challenge_id);
      this.code = '';
      this.cooldown.start();
    } catch (err) {
      this.cooldown.fromError(err);
      this.error.set(problemMessage(err, 'Could not send the code.'));
    } finally { this.busy.set(false); }
  }

  protected async verify(): Promise<void> {
    const id = this.challenge();
    if (this.busy() || !id) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await firstValueFrom(this.auth.verifyMyPhone(id, this.code));
      this.challenge.set(null);
    } catch (err) {
      this.error.set(problemMessage(err, 'That code did not work. Please try again.'));
      return;
    } finally { this.busy.set(false); }
    await this.setEnabled(true);
  }

  protected dismiss(): void {
    this.dismissed.set(true);
    try { localStorage.setItem(DISMISS_KEY, '1'); } catch { /* storage unavailable */ }
  }
}

function readDismissed(): boolean {
  try { return typeof localStorage !== 'undefined' && localStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
}

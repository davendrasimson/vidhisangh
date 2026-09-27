import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { Passkey, PasskeyService } from '@core/services/passkey.service';
import { NotificationService } from '@core/services/notification.service';
import { AuthService } from '@core/auth/auth.service';
import { AuthSession } from '@core/models/auth.models';

@Component({
  selector: 'app-security-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatIconModule, MatButtonModule],
  templateUrl: './security-settings.component.html',
})
export class SecuritySettingsComponent implements OnInit {
  private readonly passkeys = inject(PasskeyService);
  private readonly auth = inject(AuthService);
  private readonly notify = inject(NotificationService);

  protected readonly items = signal<Passkey[]>([]);
  protected readonly loading = signal(true);
  protected readonly working = signal(false);
  protected readonly supported = PasskeyService.supported();

  protected readonly sessions = signal<AuthSession[]>([]);
  protected readonly sessionsBusy = signal(false);

  async ngOnInit(): Promise<void> {
    try {
      const [passkeys, sessions] = await Promise.all([
        firstValueFrom(this.passkeys.list()),
        firstValueFrom(this.auth.sessions()),
      ]);
      this.items.set(passkeys);
      this.sessions.set(sessions);
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected deviceOf(s: AuthSession): string {
    if (s.device_label && s.device_label !== 'login' && s.device_label !== 'signup') return s.device_label;
    const ua = s.user_agent ?? '';
    const os = /Windows/.test(ua) ? 'Windows' : /Mac/.test(ua) ? 'macOS'
      : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS'
      : /Linux/.test(ua) ? 'Linux' : 'Unknown device';
    const browser = /Edg/.test(ua) ? 'Edge' : /Chrome/.test(ua) ? 'Chrome'
      : /Firefox/.test(ua) ? 'Firefox' : /Safari/.test(ua) ? 'Safari' : '';
    return browser ? `${browser} on ${os}` : os;
  }

  protected async revoke(s: AuthSession): Promise<void> {
    this.sessionsBusy.set(true);
    try {
      await firstValueFrom(this.auth.revokeSession(s.id));
      this.sessions.update((list) => list.filter((x) => x.id !== s.id));
      this.notify.success('Signed out of that device.');
    } catch {
      /* handled */
    } finally {
      this.sessionsBusy.set(false);
    }
  }

  protected async revokeOthers(): Promise<void> {
    this.sessionsBusy.set(true);
    try {
      const { revoked } = await firstValueFrom(this.auth.revokeOtherSessions());
      this.sessions.update((list) => list.filter((x) => x.is_current));
      this.notify.success(revoked ? `Signed out of ${revoked} other device(s).` : 'No other sessions.');
    } catch {
      /* handled */
    } finally {
      this.sessionsBusy.set(false);
    }
  }

  protected async add(): Promise<void> {
    if (this.working()) return;
    const name = prompt('Name this passkey (e.g. "MacBook Touch ID")')?.trim();
    if (!name) return;
    this.working.set(true);
    try {
      const created = await this.passkeys.register(name);
      this.items.update((list) => [created, ...list]);
      this.notify.success('Passkey added.');
    } catch {
      this.notify.error('Could not add the passkey. Your device may not support it, or it was cancelled.');
    } finally {
      this.working.set(false);
    }
  }

  protected async remove(p: Passkey): Promise<void> {
    this.working.set(true);
    try {
      await firstValueFrom(this.passkeys.remove(p.id));
      this.items.update((list) => list.filter((x) => x.id !== p.id));
    } catch {
      /* handled */
    } finally {
      this.working.set(false);
    }
  }
}

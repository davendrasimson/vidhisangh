import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '@core/auth/auth.service';

@Component({
  selector: 'app-whatsapp-login', standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatFormFieldModule, MatInputModule, MatButtonModule],
  template: `
    <form (ngSubmit)="challenge() ? login() : send()" class="grid gap-3">
      @if (error()) { <p role="alert" class="text-danger text-sm">{{ error() }}</p> }
      @if (info()) { <p role="status" class="text-content-muted text-sm">{{ info() }}</p> }
      <mat-form-field appearance="outline">
        <mat-label>Mobile number</mat-label>
        <input matInput type="tel" name="phone" [(ngModel)]="phone" (ngModelChange)="reset()" autocomplete="tel" placeholder="+91 9876543210" required />
      </mat-form-field>
      @if (challenge()) {
        <mat-form-field appearance="outline">
          <mat-label>WhatsApp code</mat-label>
          <input matInput name="code" [(ngModel)]="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required />
        </mat-form-field>
        @if (mfaRequired()) {
          <mat-form-field appearance="outline">
            <mat-label>Authenticator code</mat-label>
            <input matInput name="mfa" [(ngModel)]="mfa" autocomplete="one-time-code" />
          </mat-form-field>
        }
        <button mat-flat-button type="submit" [disabled]="busy() || code.length !== 6">Verify and sign in</button>
        <button mat-button type="button" [disabled]="busy()" (click)="send()">Resend WhatsApp code</button>
      } @else {
        <button mat-flat-button type="submit" [disabled]="busy() || !phone.trim()">Send WhatsApp login code</button>
      }
      <p class="text-xs text-content-muted">Use the mobile number verified when you registered. Codes arrive through the Simsondesk WhatsApp service and expire in 5 minutes.</p>
    </form>
  `,
})
export class WhatsappLoginComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  protected phone = '';
  protected code = '';
  protected mfa = '';
  protected readonly challenge = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);
  protected readonly mfaRequired = signal(false);
  protected reset(): void { this.challenge.set(null); this.code = ''; this.info.set(null); }
  protected async send(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true); this.error.set(null);
    const phone = this.phone;
    try {
      const result = await firstValueFrom(this.auth.requestWhatsAppCode(phone, 'login'));
      if (this.phone !== phone) return;
      this.challenge.set(result.challenge_id); this.code = ''; this.info.set(result.detail);
    } catch (err) { this.error.set((err as HttpErrorResponse).error?.detail ?? 'Could not send code.'); }
    finally { this.busy.set(false); }
  }
  protected async login(): Promise<void> {
    if (this.busy() || !this.challenge()) return;
    this.busy.set(true); this.error.set(null);
    try {
      const pair = await firstValueFrom(this.auth.whatsappLogin(this.challenge()!, this.code, this.mfa));
      if (pair.password_must_change) { await this.router.navigateByUrl('/auth/change-password'); return; }
      await firstValueFrom(this.auth.loadCurrentUser());
      const url = this.route.snapshot.queryParamMap.get('returnUrl') ?? '';
      await this.router.navigateByUrl(url.startsWith('/') && !url.startsWith('//') && !url.includes('\\') && !url.includes(':') ? url : '/app/dashboard');
    } catch (err) {
      const problem = (err as HttpErrorResponse).error;
      if (problem?.title === 'mfa_required') this.mfaRequired.set(true);
      this.error.set(problem?.detail ?? 'Sign in failed. Please try again.');
    } finally { this.busy.set(false); }
  }
}

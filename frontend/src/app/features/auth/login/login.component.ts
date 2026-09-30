import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { AuthService } from '@core/auth/auth.service';
import { PasskeyService } from '@core/services/passkey.service';
import { ApiProblem, SsoProvider } from '@core/models/auth.models';

import { WhatsappLoginComponent } from '../whatsapp-login.component';

export const SSO_PROVIDER_KEY = 'vs_sso_provider';

/** In-app paths only: must start with "/" (not "//"), no backslash, no scheme (A-33). */
export function safeReturnUrl(raw: string | null): string {
  return raw && raw.startsWith('/') && !raw.startsWith('//') && !raw.includes('\\') && !raw.includes(':') ? raw : '/app/dashboard';
}

@Component({
  selector: 'app-login',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule, RouterLink, WhatsappLoginComponent,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatIconModule, MatProgressBarModule,
  ],
  templateUrl: './login.component.html',
})
export class LoginComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly passkeys = inject(PasskeyService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly submitting = signal(false);
  protected readonly whatsappAvailable = signal(false);
  protected readonly whatsappMode = signal(false);
  protected async resendVerification(): Promise<void> {
    if (this.form.controls.email.invalid || this.submitting()) return;
    this.submitting.set(true);
    try {
      const result = await firstValueFrom(this.auth.resendPublicVerification(this.form.controls.email.value));
      this.infoMsg.set(result.detail);
    } catch (err) { this.handleError(err as HttpErrorResponse); }
    finally { this.submitting.set(false); }
  }
  protected readonly mfaRequired = signal(false);
  protected readonly errorMsg = signal<string | null>(null);
  protected readonly infoMsg = signal<string | null>(
    this.route.snapshot.queryParamMap.get('changed') === '1'
      ? 'Your password was changed. Sign in again with the new one.'
      : this.route.snapshot.queryParamMap.get('reason') === 'session_expired'
        ? 'Your session has expired. Sign in again to continue where you left off.'
        : null,
  );
  protected hidePassword = signal(true);
  protected readonly ssoProviders = signal<SsoProvider[]>([]);
  protected readonly passkeySupported = PasskeyService.supported();

  async ngOnInit(): Promise<void> {
    void firstValueFrom(this.auth.authOptions()).then(options => {
      this.whatsappAvailable.set(options.whatsapp_available);
    }).catch(() => {});
    try {
      this.ssoProviders.set(await firstValueFrom(this.auth.ssoProviders()));
    } catch {
      /* SSO is optional — ignore if unavailable */
    }
  }

  protected async signInWithPasskey(): Promise<void> {
    const email = this.form.controls.email.value.trim();
    if (!email) {
      this.errorMsg.set('Enter your email first, then use your passkey.');
      return;
    }
    this.submitting.set(true);
    this.errorMsg.set(null);
    try {
      await this.passkeys.authenticate(email);
      await firstValueFrom(this.auth.loadCurrentUser());
      const returnUrl = safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl'));
      await this.router.navigateByUrl(returnUrl);
    } catch (err) {
      const problem = (err as HttpErrorResponse)?.error as ApiProblem | undefined;
      this.errorMsg.set(problem?.detail ?? 'Passkey sign-in failed or was cancelled.');
    } finally {
      this.submitting.set(false);
    }
  }

  protected async startSso(provider: SsoProvider): Promise<void> {
    this.errorMsg.set(null);
    try {
      const redirectUri = `${window.location.origin}/auth/callback`;
      const { authorize_url } = await firstValueFrom(
        this.auth.ssoAuthorize(provider.name, redirectUri),
      );
      sessionStorage.setItem(SSO_PROVIDER_KEY, provider.name);
      window.location.href = authorize_url;
    } catch (err) {
      this.handleError(err as HttpErrorResponse);
    }
  }

  protected readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
    mfa_code: [''],
  });

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.submitting()) return;
    this.submitting.set(true);
    this.errorMsg.set(null);

    try {
      const { email, password, mfa_code } = this.form.getRawValue();
      const pair = await firstValueFrom(
        this.auth.login({ email, password, mfa_code: mfa_code || null }),
      );
      // A temporary (admin-issued) password can do nothing but be replaced.
      if (pair.password_must_change || this.auth.mustChangePassword()) {
        await this.router.navigateByUrl('/auth/change-password');
        return;
      }
      await firstValueFrom(this.auth.loadCurrentUser());
      const returnUrl = safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl'));
      await this.router.navigateByUrl(returnUrl);
    } catch (err) {
      this.handleError(err as HttpErrorResponse);
    } finally {
      this.submitting.set(false);
    }
  }

  private handleError(err: HttpErrorResponse): void {
    const problem = err.error as ApiProblem | undefined;
    if (problem?.title === 'mfa_required') {
      this.mfaRequired.set(true);
      this.form.controls.mfa_code.addValidators(Validators.required);
      this.errorMsg.set('Enter the 6-digit code from your authenticator app.');
      return;
    }
    this.errorMsg.set(problem?.detail ?? 'Sign in failed. Please try again.');
  }
}

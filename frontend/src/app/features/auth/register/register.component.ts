import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { AuthService } from '@core/auth/auth.service';
import { isNativeApp } from '@core/platform/platform';
import { problemMessage } from '@core/interceptors/error.interceptor';
import { STRICT_EMAIL } from '../send-code-cooldown';
import { countStep } from '@core/analytics/funnel';
import { rememberNext, takeNext } from '@core/navigation/after-signup';
import { PROFESSIONAL_ROLES } from '../professional-roles';
import { WhatsappLoginComponent } from '../whatsapp-login.component';
import { TPipe } from '@core/i18n/t.pipe';
import { UiLanguageService } from '@core/i18n/ui-language.service';
import {
  PasswordStrengthComponent,
  STRONG_PASSWORD,
} from '@shared/password-strength/password-strength.component';

/**
 * Sign-up. WhatsApp first (number → code → name and role: no password, no
 * email link to wait for); email + password is the alternative, and the
 * firm/chamber questions only appear for someone registering a firm.
 */
@Component({
  selector: 'app-register',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule, RouterLink, WhatsappLoginComponent,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatCheckboxModule,
    MatIconModule, MatProgressBarModule, MatSelectModule, PasswordStrengthComponent, TPipe,
  ],
  templateUrl: './register.component.html',
})
export class RegisterComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly i18n = inject(UiLanguageService);
  protected readonly lang = this.i18n.lang;

  protected readonly roles = PROFESSIONAL_ROLES;
  protected readonly submitting = signal(false);
  protected readonly errorMsg = signal<string | null>(null);
  protected readonly infoMsg = signal<string | null>(null);
  protected readonly pendingEmail = signal(false);
  protected readonly hidePassword = signal(true);
  /** WhatsApp is shown until the server says it is not configured. */
  protected readonly whatsappAvailable = signal(true);
  protected readonly useEmail = signal(false);
  /** "Continue with Google": web only (the app cannot receive the redirect yet). */
  protected readonly googleAvailable = signal(false);

  protected readonly form = this.fb.nonNullable.group({
    firm: [false],
    organisation_name: [''],
    full_name: ['', [Validators.required, Validators.pattern(/\s*\S(?:[\s\S]*\S)\s*/), Validators.maxLength(200)]],
    // STRICT_EMAIL alone: Validators.email rejects the trailing space phone
    // keyboards add after an autocompleted address (trimmed on submit).
    email: ['', [Validators.required, Validators.pattern(STRICT_EMAIL)]],
    professional_role: ['', [Validators.required]],
    password: ['', [Validators.required, Validators.pattern(STRONG_PASSWORD)]],
    add_sample_data: [true],
    accept_terms: [false, [Validators.requiredTrue]],
  });

  private readonly route = inject(ActivatedRoute);

  async ngOnInit(): Promise<void> {
    countStep('register_view');
    // Came from a public page ("save this section"): go there once signed in,
    // even when sign-in happens later (email verification) or on another screen.
    rememberNext(this.route.snapshot.queryParamMap.get('returnUrl'));
    if (!isNativeApp()) {
      firstValueFrom(this.auth.ssoProviders())
        .then(list => this.googleAvailable.set(list.some(p => p.name === 'google')))
        .catch(() => { /* Google stays hidden. */ });
    }
    try {
      const options = await firstValueFrom(this.auth.authOptions());
      this.whatsappAvailable.set(options.whatsapp_available);
    } catch { /* Keep WhatsApp on offer; the email form is one tap away. */ }
  }

  protected async continueWithGoogle(): Promise<void> {
    this.errorMsg.set(null);
    try {
      await this.auth.startSso('google');
    } catch (err) {
      this.errorMsg.set(problemMessage(err, this.i18n.t('Could not open Google sign-in. Please try again.')));
    }
  }

  protected showEmailForm(): void {
    this.useEmail.set(true);
    countStep('email_form_opened');
  }

  protected changeFirm(): void {
    const name = this.form.controls.organisation_name;
    name.setValidators(this.form.controls.firm.value
      ? [Validators.required, Validators.pattern(/\s*\S(?:[\s\S]*\S)\s*/), Validators.maxLength(200)] : []);
    name.updateValueAndValidity();
  }

  protected async resendVerification(): Promise<void> {
    this.submitting.set(true);
    try {
      const result = await firstValueFrom(this.auth.resendPublicVerification(this.form.controls.email.value));
      this.infoMsg.set(result.detail);
    } catch (err) {
      this.errorMsg.set(problemMessage(err, this.i18n.t('Could not resend. Please try again.')));
    } finally { this.submitting.set(false); }
  }

  /** What is still missing, in the order of the form (shown next to the button). */
  protected missing(): string[] {
    const c = this.form.controls;
    const out: string[] = [];
    if (c.full_name.invalid) out.push(this.i18n.t('your full name'));
    if (c.email.invalid) out.push(this.i18n.t('a valid email address'));
    if (c.professional_role.invalid) out.push(this.i18n.t('what best describes you'));
    if (c.password.invalid) out.push(this.i18n.t('a password of at least 8 characters with upper and lower case, a number and a symbol'));
    if (c.organisation_name.invalid) out.push(this.i18n.t('your firm or chamber name'));
    if (c.accept_terms.invalid) out.push(this.i18n.t('agreement to the Terms of Service'));
    return out;
  }

  protected async submit(): Promise<void> {
    if (this.submitting()) return;
    if (this.form.invalid) {
      // The button stays tappable: a silent disabled button on a phone looks
      // like "nothing happens". Say what is missing, next to the button.
      this.form.markAllAsTouched();
      this.errorMsg.set(`${this.i18n.t('Please add')} ${this.missing().join('; ')}.`);
      return;
    }
    this.submitting.set(true);
    this.errorMsg.set(null);
    try {
      const values = this.form.getRawValue();
      const result = await firstValueFrom(this.auth.register({
        practice_type: values.firm ? 'firm' : 'individual',
        organisation_name: values.firm ? values.organisation_name.trim() : undefined,
        full_name: values.full_name,
        email: values.email.trim(),
        professional_role: values.professional_role,
        password: values.password,
        // The guided sample workspace is for practice tools; a firm sets that up.
        add_sample_data: values.firm && values.add_sample_data,
        accept_terms: values.accept_terms,
      }));
      if ('verification_required' in result) {
        this.pendingEmail.set(true);
        this.infoMsg.set(result.detail);
        return;
      }
      await firstValueFrom(this.auth.loadCurrentUser());
      await this.router.navigateByUrl(takeNext() ?? '/app/dashboard');
    } catch (err) {
      this.errorMsg.set(problemMessage(err, this.i18n.t('Registration failed. Please try again.')));
    } finally {
      this.submitting.set(false);
    }
  }
}

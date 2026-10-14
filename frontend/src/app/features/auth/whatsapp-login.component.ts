import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatRadioModule } from '@angular/material/radio';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { AuthService } from '@core/auth/auth.service';
import { RoleVisibility, WhatsAppSignupRequired } from '@core/models/auth.models';
import { VsPhoneInputComponent } from '@shared/phone-input/vs-phone-input.component';

@Component({
  selector: 'app-whatsapp-login', standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatSelectModule, MatRadioModule, MatCheckboxModule, VsPhoneInputComponent],
  template: `
    @if (signup(); as pass) {
      <form (ngSubmit)="finishSignup()" class="grid gap-3" #signupForm="ngForm">
        <div>
          <h2 class="text-lg font-semibold text-content">Welcome to VidhiSangh</h2>
          <p class="text-sm text-content-muted">Your number is verified. A few details to create your free account.</p>
        </div>
        @if (error()) { <p role="alert" class="text-danger text-sm">{{ error() }}</p> }
        <mat-form-field appearance="outline">
          <mat-label>Full name</mat-label>
          <input matInput name="full_name" [(ngModel)]="fullName" autocomplete="name" required minlength="2" maxlength="200" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Email</mat-label>
          <input matInput type="email" name="email" [(ngModel)]="email" autocomplete="email" required email />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>I am a</mat-label>
          <mat-select name="role" [(ngModel)]="role" required>
            @for (r of roles; track r.value) { <mat-option [value]="r.value">{{ r.label }}</mat-option> }
          </mat-select>
        </mat-form-field>
        <fieldset class="grid gap-1">
          <legend class="text-sm font-medium text-content mb-1">Who can see this on your profile?</legend>
          <mat-radio-group name="visibility" [(ngModel)]="visibility" class="grid gap-1">
            <mat-radio-button value="everyone">Everyone</mat-radio-button>
            <mat-radio-button value="connections">Only my connections</mat-radio-button>
            <mat-radio-button value="none">Don't show it</mat-radio-button>
          </mat-radio-group>
        </fieldset>
        <mat-checkbox name="terms" [(ngModel)]="acceptTerms" required>
          I agree to the <a href="/terms" target="_blank" rel="noopener">Terms of Service</a> and have read the
          <a href="/privacy" target="_blank" rel="noopener">Privacy Notice</a>.
        </mat-checkbox>
        <button mat-flat-button type="submit" [disabled]="busy() || !signupForm.valid || !acceptTerms">
          {{ busy() ? 'Creating your account…' : 'Create my account' }}
        </button>
      </form>
    } @else {
    <form (ngSubmit)="challenge() ? login() : send()" class="grid gap-3">
      @if (error()) { <p role="alert" class="text-danger text-sm">{{ error() }}</p> }
      @if (info()) { <p role="status" class="text-content-muted text-sm">{{ info() }}</p> }
      <vs-phone-input name="phone" [(ngModel)]="phone" (ngModelChange)="reset()" #phoneField="ngModel" required />
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
        <button mat-flat-button type="submit" [disabled]="busy() || !phone || !!phoneField.invalid">Send WhatsApp login code</button>
      }
      <p class="text-xs text-content-muted">New to VidhiSangh? Enter your number all the same: after the code, we'll create your free account. Codes arrive on WhatsApp and expire in 5 minutes.</p>
    </form>
    }
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
  /** Set when the verified number has no account: the sign-up form is shown. */
  protected readonly signup = signal<WhatsAppSignupRequired | null>(null);
  protected fullName = '';
  protected email = '';
  protected role = '';
  protected visibility: RoleVisibility = 'everyone';
  protected acceptTerms = false;
  /** Job profiles (values from the profile masters), the common ones first. */
  protected readonly roles = [
    { value: 'advocate', label: 'Advocate' },
    { value: 'law_student', label: 'Law Student' },
    { value: 'judicial_officer', label: 'Judicial Officer' },
    { value: 'in_house_counsel', label: 'Corporate / In-house Counsel' },
    { value: 'senior_advocate', label: 'Senior Advocate' },
    { value: 'retired_judicial_officer', label: 'Retired Judicial Officer' },
    { value: 'arbitrator', label: 'Arbitrator / Mediator' },
    { value: 'law_officer', label: 'Government Law Officer' },
    { value: 'law_teacher', label: 'Law Teacher / Academic' },
    { value: 'paralegal', label: 'Paralegal' },
    { value: 'clerk', label: 'Court Clerk / Munshi' },
    { value: 'other', label: 'Other legal professional' },
  ];
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
      const result = await firstValueFrom(this.auth.whatsappLogin(this.challenge()!, this.code, this.mfa));
      if ('signup_required' in result) { this.signup.set(result); return; }
      if (result.password_must_change) { await this.router.navigateByUrl('/auth/change-password'); return; }
      await this.enterApp();
    } catch (err) {
      const problem = (err as HttpErrorResponse).error;
      if (problem?.title === 'mfa_required') this.mfaRequired.set(true);
      this.error.set(problem?.detail ?? 'Sign in failed. Please try again.');
    } finally { this.busy.set(false); }
  }

  protected async finishSignup(): Promise<void> {
    const pass = this.signup();
    if (this.busy() || !pass || !this.acceptTerms) return;
    this.busy.set(true); this.error.set(null);
    try {
      await firstValueFrom(this.auth.whatsappSignup({
        signup_id: pass.signup_id, signup_token: pass.signup_token, full_name: this.fullName.trim(),
        email: this.email.trim(), accept_terms: true, professional_role: this.role, role_visibility: this.visibility,
      }));
      await this.enterApp();
    } catch (err) {
      const problem = (err as HttpErrorResponse).error;
      if ((err as HttpErrorResponse).status === 401) {
        // The pass expired (15 minutes) or was used: start again with a new code.
        this.signup.set(null); this.reset();
        this.error.set('That took a little long. Request a new WhatsApp code to continue.');
      } else {
        this.error.set(problem?.detail ?? 'Could not create your account. Please try again.');
      }
    } finally { this.busy.set(false); }
  }

  private async enterApp(): Promise<void> {
    await firstValueFrom(this.auth.loadCurrentUser());
    const url = this.route.snapshot.queryParamMap.get('returnUrl') ?? '';
    await this.router.navigateByUrl(url.startsWith('/') && !url.startsWith('//') && !url.includes('\\') && !url.includes(':') ? url : '/app/dashboard');
  }
}

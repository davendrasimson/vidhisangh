import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatRadioModule } from '@angular/material/radio';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '@core/auth/auth.service';
import { VsPhoneInputComponent } from '@shared/phone-input/vs-phone-input.component';
import { ApiProblem } from '@core/models/auth.models';
import {
  PasswordStrengthComponent,
  STRONG_PASSWORD,
} from '@shared/password-strength/password-strength.component';

@Component({
  selector: 'app-register',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    VsPhoneInputComponent,
    ReactiveFormsModule, RouterLink,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatCheckboxModule,
    MatIconModule, MatProgressBarModule, PasswordStrengthComponent, MatRadioModule,
  ],
  templateUrl: './register.component.html',
})
export class RegisterComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly submitting = signal(false);
  protected readonly errorMsg = signal<string | null>(null);
  protected hidePassword = signal(true);
  protected readonly whatsappAvailable = signal(false);
  async ngOnInit(): Promise<void> {
    this.form.controls.phone.disable();
    try {
      const options = await firstValueFrom(this.auth.authOptions());
      this.whatsappAvailable.set(options.whatsapp_available);
      if (options.whatsapp_available) this.form.controls.phone.enable();
    } catch { /* Email registration remains available. */ }
  }

  protected readonly pendingEmail = signal(false);
  protected readonly infoMsg = signal<string | null>(null);
  protected readonly phoneChallenge = signal<string | null>(null);
  protected readonly sendingCode = signal(false);

  protected readonly form = this.fb.nonNullable.group({
    practice_type: ['individual' as 'individual' | 'firm'],
    organisation_name: [''],
    full_name: ['', [Validators.required, Validators.pattern(/\s*\S(?:[\s\S]*\S)\s*/), Validators.maxLength(200)]],
    email: ['', [Validators.email]],
    phone: ['', [Validators.pattern(/^(?:\+?[1-9][0-9 ()-]{7,20})$/)]],
    phone_code: [''],
    password: ['', [Validators.required, Validators.pattern(STRONG_PASSWORD)]],
    add_sample_data: [true],
    accept_terms: [false, [Validators.requiredTrue]],
  }, { validators: control => control.get('email')?.value?.trim() || control.get('phone')?.value?.trim()
      ? null : { contactRequired: true } });

  constructor() {
    // A new number or country invalidates a code already sent.
    this.form.controls.phone.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.phoneChanged());
  }

  protected phoneChanged(): void {
    this.phoneChallenge.set(null);
    this.form.controls.phone_code.setValue('');
  }

  protected async sendCode(): Promise<void> {
    const phone = this.form.controls.phone;
    if (!phone.value || phone.invalid || this.sendingCode()) return;
    this.sendingCode.set(true);
    this.errorMsg.set(null);
    const number = phone.value;
    try {
      const result = await firstValueFrom(this.auth.requestWhatsAppCode(number, 'register'));
      if (phone.value !== number) return;
      this.phoneChallenge.set(result.challenge_id);
      this.infoMsg.set('Enter the WhatsApp code below. It expires in 5 minutes.');
    } catch (err) {
      this.errorMsg.set((err as HttpErrorResponse).error?.detail ?? 'Could not send the code. Try again.');
    } finally { this.sendingCode.set(false); }
  }

  protected async resendVerification(): Promise<void> {
    this.submitting.set(true);
    try {
      const result = await firstValueFrom(this.auth.resendPublicVerification(this.form.controls.email.value));
      this.infoMsg.set(result.detail);
    } catch (err) {
      this.errorMsg.set((err as HttpErrorResponse).error?.detail ?? 'Could not resend. Please try again.');
    } finally { this.submitting.set(false); }
  }

  protected changePracticeType(): void {
    const name = this.form.controls.organisation_name;
    name.setValidators(this.form.controls.practice_type.value === 'firm'
      ? [Validators.required, Validators.pattern(/\s*\S(?:[\s\S]*\S)\s*/), Validators.maxLength(200)] : []);
    name.updateValueAndValidity();
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.submitting()) return;
    if (this.form.controls.phone.value && (!this.phoneChallenge() || !/^\d{6}$/.test(this.form.controls.phone_code.value))) return;
    this.submitting.set(true);
    this.errorMsg.set(null);
    try {
      const values = this.form.getRawValue();
      const result = await firstValueFrom(this.auth.register({
        ...values,
        email: values.email.trim() || null,
        phone: values.phone.trim() || null,
        phone_challenge_id: this.phoneChallenge(),
        phone_code: values.phone ? values.phone_code : null,
        organisation_name: values.practice_type === 'firm' ? values.organisation_name.trim() : undefined,
      }));
      if ('verification_required' in result) {
        this.pendingEmail.set(true);
        this.infoMsg.set(result.detail);
        return;
      }
      await firstValueFrom(this.auth.loadCurrentUser());
      await this.router.navigateByUrl('/app/dashboard');
    } catch (err) {
      const problem = (err as HttpErrorResponse).error as ApiProblem | undefined;
      this.errorMsg.set(problem?.detail ?? 'Registration failed. Please try again.');
    } finally {
      this.submitting.set(false);
    }
  }
}

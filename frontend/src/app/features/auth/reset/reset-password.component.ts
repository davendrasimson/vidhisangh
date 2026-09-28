import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { AuthService } from '@core/auth/auth.service';
import { ApiProblem } from '@core/models/auth.models';
import {
  PasswordStrengthComponent,
  STRONG_PASSWORD,
  passwordsMatch,
} from '@shared/password-strength/password-strength.component';

/** `/auth/reset/:token` — set a new password from an emailed reset link, or
 *  choose the first password from an admin invitation (`?invite=1`). */
@Component({
  selector: 'app-reset-password',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule, RouterLink,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatIconModule, MatProgressBarModule,
    PasswordStrengthComponent,
  ],
  template: `
    <div class="w-full">
      <h2 class="vs-display text-3xl font-semibold text-content">
        {{ invite ? 'Welcome to VidhiSangh' : 'Choose a new password' }}
      </h2>
      <p class="text-sm text-content-muted mt-1.5 mb-6">
        {{ invite
          ? 'Set the password you will sign in with. Your invitation link works once.'
          : 'Every other device will be signed out once your password changes.' }}
      </p>

      @if (submitting()) {
        <mat-progress-bar mode="indeterminate" class="mb-4"></mat-progress-bar>
      }

      @if (done()) {
        <div class="mb-4 rounded-lg border border-success/40 bg-success/10 px-3 py-2 text-sm text-content" role="status">
          Your password has been set. You can sign in now.
        </div>
        <a mat-flat-button color="primary" routerLink="/auth/login" class="h-11 w-full">Sign in</a>
      } @else {
        @if (errorMsg()) {
          <div class="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
            {{ errorMsg() }}
          </div>
        }
        <form [formGroup]="form" (ngSubmit)="submit()" class="grid gap-1">
          <mat-form-field appearance="outline">
            <mat-label>New password</mat-label>
            <input matInput [type]="hide() ? 'password' : 'text'" formControlName="new_password"
                   autocomplete="new-password" required />
            <button mat-icon-button matSuffix type="button" (click)="hide.set(!hide())"
                    [attr.aria-label]="hide() ? 'Show password' : 'Hide password'">
              <mat-icon class="material-icons-outlined">{{ hide() ? 'visibility' : 'visibility_off' }}</mat-icon>
            </button>
            @if (form.controls.new_password.hasError('pattern') && form.controls.new_password.touched) {
              <mat-error>At least 8 chars with upper &amp; lower case, a number, and a symbol.</mat-error>
            }
          </mat-form-field>
          <vs-password-strength [password]="form.controls.new_password.value" />
          <mat-form-field appearance="outline">
            <mat-label>Confirm password</mat-label>
            <input matInput [type]="hide() ? 'password' : 'text'" formControlName="confirm"
                   autocomplete="new-password" required />
            @if (form.hasError('mismatch') && form.controls.confirm.touched) {
              <mat-error>The passwords do not match.</mat-error>
            }
          </mat-form-field>
          <button mat-flat-button color="primary" type="submit" [disabled]="submitting() || form.invalid" class="h-11">
            {{ invite ? 'Set password and continue' : 'Change password' }}
          </button>
        </form>
        <p class="text-sm text-content-muted mt-6 text-center">
          <a routerLink="/auth/login" class="text-brand font-medium">Back to sign in</a>
        </p>
      }
    </div>
  `,
})
export class ResetPasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly token = this.route.snapshot.paramMap.get('token') ?? '';
  protected readonly invite = this.route.snapshot.queryParamMap.get('invite') === '1';
  protected readonly submitting = signal(false);
  protected readonly done = signal(false);
  protected readonly errorMsg = signal<string | null>(this.token ? null : 'This link is incomplete.');
  protected readonly hide = signal(true);

  protected readonly form = this.fb.nonNullable.group(
    {
      new_password: ['', [Validators.required, Validators.pattern(STRONG_PASSWORD)]],
      confirm: ['', [Validators.required]],
    },
    { validators: passwordsMatch },
  );

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.submitting() || !this.token) return;
    this.submitting.set(true);
    this.errorMsg.set(null);
    try {
      await firstValueFrom(this.auth.resetPassword(this.token, this.form.controls.new_password.value));
      this.done.set(true);
    } catch (err) {
      const problem = (err as HttpErrorResponse).error as ApiProblem | undefined;
      const validation = Array.isArray(problem?.errors)
        ? (problem?.errors as { msg?: string }[]).map((e) => e.msg).filter(Boolean).join(' ')
        : '';
      this.errorMsg.set(validation || problem?.detail || 'This link is invalid or has expired.');
    } finally {
      this.submitting.set(false);
    }
  }
}

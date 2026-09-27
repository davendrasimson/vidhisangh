import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { AuthService } from '@core/auth/auth.service';
import { ApiProblem } from '@core/models/auth.models';

/** "Forgot password?" — asks for an email and always reports success (no enumeration). */
@Component({
  selector: 'app-forgot-password',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatFormFieldModule, MatInputModule, MatButtonModule, MatProgressBarModule],
  template: `
    <div class="w-full">
      <h2 class="vs-display text-3xl font-semibold text-content">Reset your password</h2>
      <p class="text-sm text-content-muted mt-1.5 mb-6">
        Enter the email you sign in with. If it belongs to an account we will send a link
        that stays valid for 30 minutes.
      </p>

      @if (submitting()) {
        <mat-progress-bar mode="indeterminate" class="mb-4"></mat-progress-bar>
      }

      @if (sent()) {
        <div class="mb-4 rounded-lg border border-success/40 bg-success/10 px-3 py-2 text-sm text-content" role="status">
          If an account exists for <strong>{{ form.controls.email.value }}</strong>, a reset link is on its way.
          Check your inbox (and spam folder).
        </div>
      } @else {
        @if (errorMsg()) {
          <div class="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
            {{ errorMsg() }}
          </div>
        }
        <form [formGroup]="form" (ngSubmit)="submit()" class="grid gap-1">
          <mat-form-field appearance="outline">
            <mat-label>Email</mat-label>
            <input matInput type="email" formControlName="email" autocomplete="username" required />
            @if (form.controls.email.hasError('email') && form.controls.email.touched) {
              <mat-error>Enter a valid email address.</mat-error>
            }
          </mat-form-field>
          <button mat-flat-button color="primary" type="submit" [disabled]="submitting() || form.invalid" class="h-11">
            Send reset link
          </button>
        </form>
      }

      <p class="text-sm text-content-muted mt-6 text-center">
        <a routerLink="/auth/login" class="text-brand font-medium">Back to sign in</a>
      </p>
    </div>
  `,
})
export class ForgotPasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);

  protected readonly submitting = signal(false);
  protected readonly sent = signal(false);
  protected readonly errorMsg = signal<string | null>(null);

  protected readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
  });

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.submitting()) return;
    this.submitting.set(true);
    this.errorMsg.set(null);
    try {
      await firstValueFrom(this.auth.forgotPassword(this.form.controls.email.value.trim()));
      this.sent.set(true);
    } catch (err) {
      const problem = (err as HttpErrorResponse).error as ApiProblem | undefined;
      this.errorMsg.set(problem?.detail ?? 'Could not send the reset link. Please try again.');
    } finally {
      this.submitting.set(false);
    }
  }
}

import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
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

/** `/auth/change-password` — replace a temporary (admin-issued) password.
 *  A `password_must_change` session can reach nothing else until this is done;
 *  the API signs every session out afterwards, so the page sends the user back
 *  to the login form. */
@Component({
  selector: 'app-change-password',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule, RouterLink,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatIconModule, MatProgressBarModule,
    PasswordStrengthComponent,
  ],
  template: `
    <div class="w-full">
      <h2 class="vs-display text-3xl font-semibold text-content">Set your own password</h2>
      <p class="text-sm text-content-muted mt-1.5 mb-6">
        You signed in with a temporary password. Choose your own to continue; you will then sign in again.
      </p>

      @if (submitting()) {
        <mat-progress-bar mode="indeterminate" class="mb-4"></mat-progress-bar>
      }
      @if (errorMsg()) {
        <div class="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {{ errorMsg() }}
        </div>
      }

      <form [formGroup]="form" (ngSubmit)="submit()" class="grid gap-1">
        <mat-form-field appearance="outline">
          <mat-label>Temporary password</mat-label>
          <input matInput type="password" formControlName="current_password" autocomplete="current-password" required />
          </mat-form-field>
          <vs-password-strength [password]="form.controls.new_password.value" />
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
        <mat-form-field appearance="outline">
          <mat-label>Confirm new password</mat-label>
          <input matInput [type]="hide() ? 'password' : 'text'" formControlName="confirm" autocomplete="new-password" required />
          @if (form.hasError('mismatch') && form.controls.confirm.touched) {
            <mat-error>The passwords do not match.</mat-error>
          }
        </mat-form-field>
        <button mat-flat-button color="primary" type="submit" [disabled]="submitting() || form.invalid" class="h-11">
          Change password
        </button>
      </form>

      <p class="text-sm text-content-muted mt-6 text-center">
        <a routerLink="/auth/login" class="text-brand font-medium" (click)="signOut()">Sign out instead</a>
      </p>
    </div>
  `,
})
export class ChangePasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly submitting = signal(false);
  protected readonly errorMsg = signal<string | null>(null);
  protected readonly hide = signal(true);

  protected readonly form = this.fb.nonNullable.group(
    {
      current_password: ['', [Validators.required]],
      new_password: ['', [Validators.required, Validators.pattern(STRONG_PASSWORD)]],
      confirm: ['', [Validators.required]],
    },
    { validators: passwordsMatch },
  );

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.submitting()) return;
    this.submitting.set(true);
    this.errorMsg.set(null);
    const { current_password, new_password } = this.form.getRawValue();
    try {
      await firstValueFrom(this.auth.changePassword(current_password, new_password));
      await this.auth.logout();
      await this.router.navigate(['/auth/login'], { queryParams: { changed: 1 } });
    } catch (err) {
      const problem = (err as HttpErrorResponse).error as ApiProblem | undefined;
      const validation = Array.isArray(problem?.errors)
        ? (problem?.errors as { msg?: string }[]).map((e) => e.msg).filter(Boolean).join(' ')
        : '';
      this.errorMsg.set(validation || problem?.detail || 'Could not change the password. Please try again.');
    } finally {
      this.submitting.set(false);
    }
  }

  protected signOut(): void {
    void this.auth.logout();
  }
}

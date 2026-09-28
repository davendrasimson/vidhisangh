import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { AuthService } from '@core/auth/auth.service';
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
    ReactiveFormsModule, RouterLink,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatCheckboxModule,
    MatIconModule, MatProgressBarModule, PasswordStrengthComponent,
  ],
  templateUrl: './register.component.html',
})
export class RegisterComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly submitting = signal(false);
  protected readonly errorMsg = signal<string | null>(null);
  protected hidePassword = signal(true);

  protected readonly form = this.fb.nonNullable.group({
    organisation_name: ['', [Validators.required, Validators.minLength(2)]],
    full_name: ['', [Validators.required, Validators.minLength(2)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.pattern(STRONG_PASSWORD)]],
    accept_terms: [false, [Validators.requiredTrue]],
  });

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.submitting()) return;
    this.submitting.set(true);
    this.errorMsg.set(null);
    try {
      await firstValueFrom(this.auth.register(this.form.getRawValue()));
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

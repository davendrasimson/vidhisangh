import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { AuthService } from '@core/auth/auth.service';
import { ApiProblem } from '@core/models/auth.models';

/** `/auth/verify-email/:token` — landing page for the verification email. */
@Component({
  selector: 'app-verify-email',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatButtonModule, MatProgressBarModule],
  template: `
    <div class="w-full text-center">
      @if (state() === 'working') {
        <h2 class="text-xl font-bold text-content mb-4">Confirming your email…</h2>
        <mat-progress-bar mode="indeterminate"></mat-progress-bar>
      } @else if (state() === 'ok') {
        <h2 class="vs-display text-3xl font-semibold text-content">Email confirmed</h2>
        <p class="text-sm text-content-muted mt-2 mb-6">Thank you — your address is verified.</p>
        <a mat-flat-button color="primary" routerLink="/auth/login" class="h-11 w-full">Sign in</a>
      } @else {
        <h2 class="text-xl font-bold text-content mb-2">We could not confirm this link</h2>
        <p class="text-sm text-danger mb-6">{{ error() }}</p>
        <a mat-flat-button color="primary" routerLink="/auth/login" class="h-11 w-full">Sign in</a>
      }
    </div>
  `,
})
export class VerifyEmailComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);

  protected readonly state = signal<'working' | 'ok' | 'error'>('working');
  protected readonly error = signal<string>('');

  async ngOnInit(): Promise<void> {
    const token = this.route.snapshot.paramMap.get('token');
    if (!token) {
      this.error.set('This link is incomplete.');
      this.state.set('error');
      return;
    }
    try {
      await firstValueFrom(this.auth.verifyEmail(token));
      this.state.set('ok');
    } catch (err) {
      const problem = (err as HttpErrorResponse).error as ApiProblem | undefined;
      this.error.set(problem?.detail ?? 'The link is invalid or has expired.');
      this.state.set('error');
    }
  }
}

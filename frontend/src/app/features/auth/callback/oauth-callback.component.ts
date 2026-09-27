import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { AuthService } from '@core/auth/auth.service';
import { ApiProblem } from '@core/models/auth.models';
import { SSO_PROVIDER_KEY } from '../login/login.component';

@Component({
  selector: 'app-oauth-callback',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatProgressBarModule],
  template: `
    <div class="w-full max-w-sm text-center">
      @if (error()) {
        <h2 class="text-xl font-bold text-content mb-2">Sign-in failed</h2>
        <p class="text-sm text-danger mb-6">{{ error() }}</p>
        <a routerLink="/auth/login" class="text-brand font-medium">Back to sign in</a>
      } @else {
        <h2 class="text-xl font-bold text-content mb-4">Completing sign-in…</h2>
        <mat-progress-bar mode="indeterminate"></mat-progress-bar>
      }
    </div>
  `,
})
export class OAuthCallbackComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly error = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    const params = this.route.snapshot.queryParamMap;
    const code = params.get('code');
    const state = params.get('state');
    const provider = sessionStorage.getItem(SSO_PROVIDER_KEY);
    sessionStorage.removeItem(SSO_PROVIDER_KEY);

    const providerError = params.get('error');
    if (providerError) {
      this.error.set(params.get('error_description') ?? 'The provider denied the request.');
      return;
    }
    if (!code || !state || !provider) {
      this.error.set('This sign-in link is invalid or has expired.');
      return;
    }

    try {
      await firstValueFrom(this.auth.ssoCallback(provider, code, state));
      await firstValueFrom(this.auth.loadCurrentUser());
      await this.router.navigateByUrl('/app/dashboard');
    } catch (err) {
      const problem = (err as HttpErrorResponse).error as ApiProblem | undefined;
      this.error.set(problem?.detail ?? 'We could not complete sign-in. Please try again.');
    }
  }
}

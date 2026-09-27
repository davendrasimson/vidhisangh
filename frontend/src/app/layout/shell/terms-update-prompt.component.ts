import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '@core/auth/auth.service';
import { environment } from '@env/environment';

interface LegalVersions {
  terms_version: string;
  notice_version: string;
}

/** Blocks continued use when the published legal terms are newer than the
 * authenticated user's recorded acceptance. */
@Component({
  selector: 'vs-terms-update-prompt',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    @if (required()) {
      <div class="backdrop" role="presentation">
        <section class="prompt" role="dialog" aria-modal="true" aria-labelledby="terms-title">
          <span class="icon"><mat-icon class="material-icons-outlined">policy</mat-icon></span>
          <p class="eyebrow">Privacy and terms update</p>
          <h2 id="terms-title">Please review the current legal terms</h2>
          <p class="copy">
            We have updated the Terms of Service and Privacy Notice. Review both documents,
            then record your acceptance to continue using VidhiSangh.
          </p>
          <div class="links">
            <a routerLink="/terms" target="_blank">Terms of Service</a>
            <a routerLink="/privacy" target="_blank">Privacy Notice</a>
          </div>
          @if (error()) { <p class="error">{{ error() }}</p> }
          <button type="button" (click)="accept()" [disabled]="saving()">
            {{ saving() ? 'Recording acceptance…' : 'I accept the current terms' }}
          </button>
          <p class="version">Terms {{ versions()?.terms_version }} · Notice {{ versions()?.notice_version }}</p>
        </section>
      </div>
    }
  `,
  styles: [`
    .backdrop { position: fixed; inset: 0; z-index: 2000; display: grid; place-items: center; padding: 1rem; background: rgb(9 18 40 / .74); backdrop-filter: blur(6px); }
    .prompt { width: min(31rem, 100%); border-radius: 18px; padding: 2rem; text-align: center; color: rgb(var(--vs-content)); background: rgb(var(--vs-surface-raised)); border: 1px solid rgb(var(--vs-line)); box-shadow: 0 28px 80px rgb(0 0 0 / .3); }
    .icon { display: grid; place-items: center; width: 52px; height: 52px; margin: 0 auto 1rem; border-radius: 15px; color: rgb(var(--vs-brand)); background: color-mix(in srgb, rgb(var(--vs-brand)) 13%, transparent); }
    .icon mat-icon { width: 28px; height: 28px; font-size: 28px; }
    .eyebrow { margin: 0; color: rgb(var(--vs-brand)); font-size: .72rem; font-weight: 700; letter-spacing: .11em; text-transform: uppercase; }
    h2 { margin: .45rem 0 .65rem; font-family: var(--vs-font-display); font-size: 1.65rem; line-height: 1.2; }
    .copy, .version { color: rgb(var(--vs-text-muted)); }
    .copy { line-height: 1.55; }
    .links { display: flex; justify-content: center; gap: 1rem; margin: 1rem 0 1.25rem; }
    a { color: rgb(var(--vs-brand)); font-weight: 600; }
    button { width: 100%; border: 0; border-radius: 10px; padding: .75rem 1rem; color: #fff; background: rgb(var(--vs-brand)); font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .65; cursor: wait; }
    .version { margin: .75rem 0 0; font-size: .75rem; }
    .error { margin: 0 0 .75rem; color: rgb(var(--vs-danger)); font-size: .85rem; }
  `],
})
export class TermsUpdatePromptComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  protected readonly versions = signal<LegalVersions | null>(null);
  protected readonly required = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal('');

  async ngOnInit(): Promise<void> {
    try {
      const versions = await firstValueFrom(
        this.http.get<LegalVersions>(`${environment.apiBaseUrl}/privacy/notice`),
      );
      this.versions.set(versions);
      this.required.set(this.auth.user()?.terms_version !== versions.terms_version);
    } catch {
      // A legal-status endpoint outage must not create an unrecoverable login loop.
    }
  }

  protected async accept(): Promise<void> {
    this.saving.set(true);
    this.error.set('');
    try {
      await firstValueFrom(this.auth.acceptCurrentTerms());
      this.required.set(false);
    } catch {
      this.error.set('We could not record your acceptance. Please try again.');
    } finally {
      this.saving.set(false);
    }
  }
}

import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { catchError, of } from 'rxjs';
import { environment } from '@env/environment';
import { renderMarkdown } from './legal-text';

export interface PrivacyNoticeFacts {
  terms_version: string;
  notice_version: string;
  grievance_officer: { name: string; email: string; address: string };
  notice_url: string;
  terms_url: string;
  legal_hold_years: number;
  tenant_erase_grace_days: number;
  retention_days: Record<string, number>;
  data_protection_board_url: string;
  sub_processors: { name: string; purpose: string; data: string }[];
  hosting_region: string;
}

/**
 * Shared shell for the public legal pages (/privacy, /terms): renders the
 * document from its Markdown source and, for the notice, the live grievance
 * officer details from the API so the page never goes stale.
 */
@Component({
  selector: 'vs-legal-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <div class="min-h-screen bg-surface-sunken">
      <header class="bg-surface-raised border-b border-line">
        <div class="mx-auto w-full max-w-3xl px-4 py-4 flex items-center gap-3">
          <a routerLink="/" class="font-semibold text-content">VidhiSangh</a>
          <span class="text-sm text-content-muted">· {{ title() }}</span>
          <nav class="ml-auto flex gap-4 text-sm">
            <a routerLink="/privacy" class="text-brand">Privacy notice</a>
            <a routerLink="/terms" class="text-brand">Terms</a>
            <a routerLink="/auth/login" class="text-content-muted">Sign in</a>
          </nav>
        </div>
      </header>
      <main class="mx-auto w-full max-w-3xl px-4 py-8">
        @if (facts(); as f) {
          <aside class="rounded-card bg-surface-raised border border-line shadow-card p-4 mb-6 text-sm">
            <p class="text-xs font-semibold uppercase tracking-wide text-content-muted mb-2">Grievance Officer (DPDP Act s.8(9), s.13)</p>
            <p class="font-medium text-content">{{ f.grievance_officer.name }}</p>
            <p><a class="text-brand" [href]="'mailto:' + f.grievance_officer.email">{{ f.grievance_officer.email }}</a></p>
            <p class="text-content-muted">{{ f.grievance_officer.address }}</p>
            <p class="text-content-muted mt-2">
              Current versions — Terms {{ f.terms_version }} · Notice {{ f.notice_version }} · Data hosted in {{ f.hosting_region }}.
              Unresolved grievances may be taken to the
              <a class="text-brand" [href]="f.data_protection_board_url" target="_blank" rel="noopener noreferrer">Data Protection Board of India</a>.
            </p>
          </aside>
        }
        <article class="vs-legal rounded-card bg-surface-raised border border-line shadow-card p-6" [innerHTML]="html()"></article>
      </main>
    </div>
  `,
  styles: [
    `
      .vs-legal :is(h1, h2, h3, h4) { color: rgb(var(--vs-content)); font-weight: 600; margin: 1.4em 0 0.5em; line-height: 1.25; }
      .vs-legal h1 { font-size: 1.75rem; margin-top: 0; }
      .vs-legal h2 { font-size: 1.25rem; }
      .vs-legal h3 { font-size: 1.05rem; }
      .vs-legal p, .vs-legal li { line-height: 1.6; margin: 0.5em 0; }
      .vs-legal ul, .vs-legal ol { padding-left: 1.4em; }
      .vs-legal ul { list-style: disc; }
      .vs-legal ol { list-style: decimal; }
      .vs-legal table { width: 100%; border-collapse: collapse; margin: 0.8em 0 1.2em; font-size: 0.92rem; display: block; overflow-x: auto; }
      .vs-legal th, .vs-legal td { border: 1px solid rgb(var(--vs-line)); padding: 0.45em 0.6em; text-align: left; vertical-align: top; }
      .vs-legal th { background: color-mix(in srgb, rgb(var(--vs-brand)) 8%, transparent); }
      .vs-legal code { font-size: 0.85em; padding: 0.1em 0.3em; border-radius: 4px; background: color-mix(in srgb, rgb(var(--vs-content)) 8%, transparent); }
      .vs-legal a { color: rgb(var(--vs-brand)); text-decoration: underline; }
      .vs-legal hr { border: 0; border-top: 1px solid rgb(var(--vs-line)); margin: 1.5em 0; }
    `,
  ],
})
export class LegalPageComponent {
  private readonly sanitizer = inject(DomSanitizer);
  private readonly http = inject(HttpClient);

  readonly title = input.required<string>();
  readonly markdown = input.required<string>();
  readonly showFacts = input(true);

  protected readonly html = computed(() => this.sanitizer.bypassSecurityTrustHtml(renderMarkdown(this.markdown())));
  private readonly loaded = toSignal(
    this.http.get<PrivacyNoticeFacts>(`${environment.apiBaseUrl}/privacy/notice`).pipe(catchError(() => of(null))),
    { initialValue: null },
  );
  protected readonly facts = computed(() => (this.showFacts() ? this.loaded() : null));
}

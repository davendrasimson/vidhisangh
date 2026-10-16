import { ChangeDetectionStrategy, Component, ViewEncapsulation, computed, inject, input } from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';
import { toSignal } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { catchError, of } from 'rxjs';
import { environment } from '@env/environment';
import { legalToc, renderMarkdown } from './legal-text';

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
import { PublicFooterComponent, PublicHeaderComponent } from '@shared/public-chrome/public-chrome.component';

@Component({
  selector: 'vs-legal-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PublicHeaderComponent, PublicFooterComponent],
  // None: the document arrives as HTML via [innerHTML], which component-scoped
  // styles never reach (headings and tables used to render unstyled).
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="vs-legal-page">
      <vs-public-header />
      <div class="vs-legal-wrap">
        <aside class="vs-legal-side">
          @if (toc().length) {
            <nav class="vs-legal-toc vs-legal-toc--wide" aria-label="On this page">
              <p class="vs-legal-side__title">On this page</p>
              <ol>
                @for (t of toc(); track t.id) { <li><a [href]="'#' + t.id" (click)="jump($event, t.id)">{{ t.text }}</a></li> }
              </ol>
            </nav>
            <details class="vs-legal-toc vs-legal-toc--narrow">
              <summary>On this page ({{ toc().length }} sections)</summary>
              <ol>
                @for (t of toc(); track t.id) { <li><a [href]="'#' + t.id" (click)="jump($event, t.id)">{{ t.text }}</a></li> }
              </ol>
            </details>
          }
          @if (facts(); as f) {
            <section class="vs-legal-card" aria-label="Grievance Officer">
              <p class="vs-legal-side__title">Grievance Officer · DPDP Act s.8(9), s.13</p>
              <p class="vs-legal-card__name">{{ f.grievance_officer.name }}</p>
              <p><a [href]="'mailto:' + f.grievance_officer.email">{{ f.grievance_officer.email }}</a></p>
              <p class="vs-legal-muted">{{ f.grievance_officer.address }}</p>
              <p class="vs-legal-muted vs-legal-small">
                Terms {{ f.terms_version }} · Notice {{ f.notice_version }} · Data hosted in {{ f.hosting_region }}.
                Unresolved grievances may go to the
                <a [href]="f.data_protection_board_url" target="_blank" rel="noopener noreferrer">Data Protection Board of India</a>.
              </p>
            </section>
          }
        </aside>
        <article class="vs-legal" [innerHTML]="html()"></article>
      </div>
      <vs-public-footer />
    </div>
  `,
  styles: [
    `
      .vs-legal-page { min-height: 100vh; background: rgb(var(--vs-surface-sunken)); color: rgb(var(--vs-content)); }
      .vs-legal-wrap { display: grid; grid-template-columns: 17rem minmax(0, 1fr); gap: 2rem; align-items: start;
        width: min(1120px, calc(100% - 2rem)); margin: 0 auto; padding: 2rem 0 3rem; }
      .vs-legal-side { position: sticky; top: 5.5rem; display: grid; gap: 1rem; max-height: calc(100vh - 7rem); overflow-y: auto; }
      .vs-legal-side__title { margin: 0 0 .5rem; color: rgb(var(--vs-text-muted)); font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
      .vs-legal-toc ol { margin: 0; padding: 0; list-style: none; display: grid; gap: .15rem; }
      .vs-legal-toc a { display: block; padding: .3rem .5rem; border-radius: 8px; color: rgb(var(--vs-content)); font-size: .88rem; line-height: 1.35; text-decoration: none; }
      .vs-legal-toc a:hover { background: color-mix(in srgb, rgb(var(--vs-brand)) 8%, transparent); color: rgb(var(--vs-brand)); }
      .vs-legal-toc--narrow { display: none; }
      .vs-legal-card { padding: 1rem; border: 1px solid rgb(var(--vs-line)); border-radius: 14px; background: rgb(var(--vs-surface-raised)); font-size: .88rem; }
      .vs-legal-card p { margin: .2rem 0; } .vs-legal-card a { color: rgb(var(--vs-brand)); }
      .vs-legal-card__name { font-weight: 600; }
      .vs-legal-muted { color: rgb(var(--vs-text-muted)); } .vs-legal-small { font-size: .8rem; margin-top: .5rem !important; }

      .vs-legal { padding: clamp(1.25rem, 4vw, 2.75rem); border: 1px solid rgb(var(--vs-line)); border-radius: 18px; background: rgb(var(--vs-surface-raised));
        box-shadow: var(--vs-shadow-card, 0 1px 2px rgb(0 0 0 / .04)); font-size: 1rem; line-height: 1.7; overflow-wrap: break-word; }
      .vs-legal > * { max-width: 46rem; }
      .vs-legal :is(h1, h2, h3, h4) { color: rgb(var(--vs-content)); line-height: 1.25; scroll-margin-top: 5.5rem; }
      .vs-legal h1 { margin: 0 0 .35rem; font-family: var(--vs-font-display); font-size: clamp(1.7rem, 4vw, 2.3rem); font-weight: 700; }
      .vs-legal h1 + p { color: rgb(var(--vs-text-muted)); font-weight: 600; }
      .vs-legal h2 { margin: 2.2rem 0 .6rem; padding-top: 1.2rem; border-top: 1px solid rgb(var(--vs-line)); font-size: 1.3rem; font-weight: 700; }
      .vs-legal h3 { margin: 1.4rem 0 .4rem; font-size: 1.08rem; font-weight: 700; }
      .vs-legal p, .vs-legal li { margin: .55rem 0; }
      .vs-legal ul, .vs-legal ol { padding-left: 1.4rem; } .vs-legal ul { list-style: disc; } .vs-legal ol { list-style: decimal; }
      .vs-legal a { color: rgb(var(--vs-brand)); text-decoration: underline; text-underline-offset: 2px; }
      .vs-legal strong { font-weight: 650; }
      .vs-legal hr { border: 0; border-top: 1px solid rgb(var(--vs-line)); margin: 1.5rem 0; max-width: none; }
      .vs-legal hr:has(+ h2) { display: none; } /* the section rule already divides */
      .vs-legal th:nth-child(-n+2), .vs-legal td:nth-child(2) { min-width: 7.5rem; }
      .vs-legal code { font-size: .85em; padding: .1em .3em; border-radius: 4px; background: color-mix(in srgb, rgb(var(--vs-content)) 8%, transparent); }
      .vs-legal table { width: 100%; max-width: none; margin: .9rem 0 1.4rem; border-collapse: separate; border-spacing: 0; font-size: .92rem;
        border: 1px solid rgb(var(--vs-line)); border-radius: 12px; overflow: hidden; }
      .vs-legal th, .vs-legal td { padding: .6rem .75rem; text-align: left; vertical-align: top; border-bottom: 1px solid rgb(var(--vs-line)); }
      .vs-legal tr:last-child td { border-bottom: 0; }
      .vs-legal th { background: color-mix(in srgb, rgb(var(--vs-brand)) 8%, rgb(var(--vs-surface-raised))); font-weight: 700; font-size: .82rem; }
      .vs-legal tbody tr:nth-child(even) td { background: color-mix(in srgb, rgb(var(--vs-content)) 2.5%, transparent); }

      @media (max-width: 900px) {
        .vs-legal-wrap { grid-template-columns: 1fr; gap: 1rem; padding-top: 1rem; width: calc(100% - 1.5rem); }
        .vs-legal-side { position: static; max-height: none; overflow: visible; }
        .vs-legal-toc--wide { display: none; }
        .vs-legal-toc--narrow { display: block; padding: .75rem 1rem; border: 1px solid rgb(var(--vs-line)); border-radius: 14px; background: rgb(var(--vs-surface-raised)); }
        .vs-legal-toc--narrow summary { cursor: pointer; font-weight: 600; font-size: .92rem; }
        .vs-legal-toc--narrow ol { margin-top: .5rem; }
      }
      /* Phones: each table row becomes a card that names its columns. */
      @media (max-width: 640px) {
        .vs-legal { border-radius: 14px; font-size: .98rem; }
        .vs-legal table, .vs-legal tbody, .vs-legal tr, .vs-legal td { display: block; width: 100%; }
        .vs-legal table { border: 0; border-radius: 0; }
        .vs-legal thead { display: none; }
        .vs-legal tr { margin: 0 0 .75rem; border: 1px solid rgb(var(--vs-line)); border-radius: 12px; overflow: hidden; }
        .vs-legal tbody tr:nth-child(even) td { background: none; }
        .vs-legal td { border-bottom: 1px solid rgb(var(--vs-line)); }
        .vs-legal td::before { content: attr(data-label); display: block; margin-bottom: .15rem; color: rgb(var(--vs-text-muted)); font-size: .72rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
        .vs-legal td:first-child { background: color-mix(in srgb, rgb(var(--vs-brand)) 6%, rgb(var(--vs-surface-raised))) !important; font-weight: 600; }
      }
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
  protected readonly toc = computed(() => legalToc(this.markdown()));

  /** In-page jump (a bare "#id" link would make the router leave the page). */
  protected jump(event: Event, id: string): void {
    event.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    (event.target as HTMLElement).closest('details')?.removeAttribute('open');
  }
}

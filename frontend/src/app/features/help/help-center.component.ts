import { ChangeDetectionStrategy, Component, ElementRef, afterRenderEffect, computed, inject, signal, viewChild } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { HELP_TOPICS } from './help-content';
import { HelpService } from './help.service';

import { CONTACT_EMAIL, WHATSAPP_LINK, WHATSAPP_NUMBER } from '@core/contact';

import { PublicFooterComponent, PublicHeaderComponent } from '@shared/public-chrome/public-chrome.component';

@Component({
  selector: 'app-help-center',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatButtonModule, MatIconModule, PublicHeaderComponent, PublicFooterComponent],
  template: `
    @if (publicPage) { <vs-public-header /> }
    <div class="help-center">
      <header>
        <div><h1 #pageTitle tabindex="-1">Help & feature tour</h1><p>Discover what you can do with VidhiSangh, or find help for a specific page.</p></div>
        <button mat-flat-button (click)="help.open('tour')"><mat-icon>explore</mat-icon>Take a feature tour</button>
      </header>
      @if (selected(); as topic) {
        <article #guide tabindex="-1" aria-labelledby="guide-title">
          <a mat-button [routerLink]="help.libraryPath()">All help topics</a>
          <h2 id="guide-title">{{ topic.title }}</h2><p>{{ topic.summary }}</p>
          <ol>@for (step of topic.steps; track $index) { <li>{{ step }}</li> }</ol>
          <aside><mat-icon aria-hidden="true">lightbulb</mat-icon><p>{{ topic.tip }}</p></aside>
        </article>
      }
      <section aria-labelledby="features-title">
        <h2 id="features-title">Explore the product</h2>
        <p>Start with these prominent features. Availability depends on your role, plan and configured services.</p>
        <div class="feature-grid">
          @for (topic of featured; track topic.id) {
            <a [routerLink]="help.libraryPath()" [queryParams]="{ topic: topic.id }"><strong>{{ topic.title }}</strong><span>{{ topic.summary }}</span></a>
          }
        </div>
      </section>
      <section aria-labelledby="topics-title">
        <h2 id="topics-title">All help topics</h2>
        <label for="help-search">Search help</label>
        <input id="help-search" type="search" placeholder="Try custom fields, e-signatures or KYC" [value]="search()" (input)="search.set($any($event.target).value)" />
        <p aria-live="polite">{{ filtered().length }} {{ filtered().length === 1 ? 'topic' : 'topics' }}</p>
        <div class="feature-grid">
          @for (topic of filtered(); track topic.id) {
            <a [routerLink]="help.libraryPath()" [queryParams]="{ topic: topic.id }"><strong>{{ topic.title }}</strong><span>{{ topic.summary }}</span></a>
          } @empty { <p>No help topics match. Try a feature name or clear your search.</p> }
        </div>
      </section>
      @if (!publicPage) {
      <section aria-labelledby="contact-title" class="contact">
        <h2 id="contact-title">Contact us</h2>
        <p>VidhiSangh is developed and managed by <a routerLink="/about">Simson Softwares Private Limited</a>.</p>
        <p>WhatsApp: <a [href]="whatsappLink" target="_blank" rel="noopener">{{ whatsappNumber }}</a> ·
          Email: <a [href]="'mailto:' + contactEmail">{{ contactEmail }}</a></p>
      </section>
      }
    </div>
    @if (publicPage) { <vs-public-footer /> }
  `,
  styles: [`
    .help-center { max-width: 1100px; margin: auto; padding: 1rem; color: rgb(var(--vs-text)); }
    header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem; }
    h1 { font-size: 2rem; font-weight: 700; } h2 { font-size: 1.4rem; font-weight: 600; margin: 1rem 0; }
    p, li { line-height: 1.7; } section { margin: 2rem 0; }
    article { margin: 1.5rem 0; padding: 1.25rem; background: rgb(var(--vs-surface-raised)); border: 2px solid rgb(var(--vs-brand)); border-radius: 12px; }
    ol { list-style: decimal; padding-left: 1.5rem; } li { margin: .6rem 0; }
    aside { display: flex; align-items: start; gap: .6rem; margin: 1rem 0; } aside mat-icon { flex-shrink: 0; }
    .feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: .8rem; margin-top: 1rem; }
    .feature-grid a { padding: 1rem; border: 1px solid rgb(var(--vs-border)); border-radius: 10px; background: rgb(var(--vs-surface-raised)); text-decoration: none; color: inherit; }
    .feature-grid a:hover { border-color: rgb(var(--vs-brand)); }
    a:focus-visible, input:focus-visible { outline: 3px solid rgb(var(--vs-brand)); outline-offset: 3px; }
    strong, span, label { display: block; } span { margin-top: .4rem; font-size: .9rem; }
    input { display: block; width: 100%; padding: .8rem; margin: .5rem 0; border: 1px solid rgb(var(--vs-border)); border-radius: 8px; background: rgb(var(--vs-surface-raised)); color: inherit; }
  `],
})
export class HelpCenterComponent {
  protected readonly whatsappNumber = WHATSAPP_NUMBER;
  protected readonly whatsappLink = WHATSAPP_LINK;
  protected readonly contactEmail = CONTACT_EMAIL;
  /** /help (public): the site header and footer; /app/help sits inside the app. */
  protected readonly publicPage = inject(ActivatedRoute).snapshot.data['publicChrome'] === true;
  readonly help = inject(HelpService);
  private readonly params = toSignal(inject(ActivatedRoute).queryParamMap);
  readonly selected = computed(() => HELP_TOPICS.find(topic => topic.id === this.params()?.get('topic')));
  private readonly guide = viewChild<ElementRef<HTMLElement>>('guide');
  private readonly pageTitle = viewChild<ElementRef<HTMLElement>>('pageTitle');
  constructor() {
    // Bring a newly selected article into view, including keyboard/screen-reader
    // navigation from cards below the fold on the same help route.
    afterRenderEffect(() => {
      const target = this.selected() ? this.guide() : this.pageTitle();
      target?.nativeElement.focus();
    });
  }
  readonly featured = HELP_TOPICS.filter(topic => topic.featured);
  readonly search = signal('');
  readonly filtered = computed(() => {
    const query = this.search().trim().toLocaleLowerCase();
    return HELP_TOPICS.filter(topic => [topic.title, topic.summary, topic.tip, ...topic.steps].join(' ').toLocaleLowerCase().includes(query));
  });
}

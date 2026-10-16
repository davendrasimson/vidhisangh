import { ChangeDetectionStrategy, Component, afterNextRender, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TokenService } from '@core/auth/token.service';
import { CONTACT_EMAIL, WHATSAPP_LINK, WHATSAPP_NUMBER } from '@core/contact';

/**
 * The site header and footer of every public page (About, Help, Privacy,
 * Terms, Trust; the home page uses the same footer), styled like the home
 * page. A device that is signed in sees "Open app" instead of Join / Sign in.
 */
@Component({
  selector: 'vs-public-header',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <header class="vs-ph">
      <a routerLink="/" class="vs-ph__brand" aria-label="VidhiSangh home">
        <img src="/brand-mark.svg?v=4" alt="" width="34" height="34" /><span class="vs-wordmark">Vidhi<b>Sangh</b></span>
      </a>
      <nav class="vs-ph__nav" aria-label="Site">
        <a href="/acts/">Bare Acts</a>
        <a href="/judgments/">Judgments</a>
        <a routerLink="/help">Help</a>
        <a routerLink="/about">About</a>
      </nav>
      <div class="vs-ph__auth">
        @if (signedIn()) {
          <a routerLink="/app/dashboard" class="vs-ph__join">Open app</a>
        } @else {
          <a routerLink="/auth/register" class="vs-ph__join">Join now</a>
          <a routerLink="/auth/login" class="vs-ph__signin">Sign in</a>
        }
      </div>
    </header>
  `,
  styles: [`
    :host { display: block; position: sticky; top: 0; z-index: 10; }
    .vs-ph { display: flex; align-items: center; gap: 1.5rem; padding: .75rem max(1rem, calc((100vw - 1160px) / 2)); background: rgb(var(--vs-surface-raised) / .92); backdrop-filter: blur(10px); border-bottom: 1px solid rgb(var(--vs-line)); }
    a { text-decoration: none; }
    .vs-ph__brand { display: flex; align-items: center; gap: .55rem; color: rgb(var(--vs-content)); font-size: 1.45rem; }
    .vs-ph__nav { display: flex; gap: 1.25rem; } .vs-ph__nav a { color: rgb(var(--vs-text-muted)); font-size: .9rem; font-weight: 500; } .vs-ph__nav a:hover { color: rgb(var(--vs-content)); }
    .vs-ph__auth { display: flex; align-items: center; gap: .5rem; margin-left: auto; }
    .vs-ph__join { padding: .7rem 1.4rem; border-radius: 999px; color: #fff; background: linear-gradient(135deg, #215dcc, #4934b8); font-weight: 700; font-size: .98rem; box-shadow: 0 8px 20px -8px rgb(33 93 204 / .7); }
    .vs-ph__join:hover { filter: brightness(1.08); }
    .vs-ph__signin { padding: .62rem 1.3rem; border-radius: 999px; border: 2px solid #215dcc; color: #215dcc; font-weight: 700; font-size: .98rem; }
    .vs-ph__signin:hover { background: rgb(33 93 204 / .08); }
    @media (max-width: 860px) {
      .vs-ph { gap: .75rem; } .vs-ph__nav { display: none; }
      .vs-ph__brand .vs-wordmark { font-size: 1.2rem; }
      .vs-ph__join { padding: .55rem 1rem; font-size: .9rem; } .vs-ph__signin { padding: .48rem .95rem; font-size: .9rem; }
    }
  `],
})
export class PublicHeaderComponent {
  private readonly tokens = inject(TokenService);
  protected readonly signedIn = signal(false);
  constructor() {
    // Browser only (pages are prerendered): the session marker lives in localStorage.
    afterNextRender(() => this.signedIn.set(this.tokens.hasSession));
  }
}

@Component({
  selector: 'vs-public-footer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <footer class="vs-pf">
      <div class="vs-pf__brand"><img src="/brand-mark.svg?v=4" alt="" width="26" height="26" /><span class="vs-wordmark">Vidhi<b>Sangh</b></span></div>
      <nav aria-label="Legal and help">
        <a href="/acts/">Bare Acts</a>
        <a href="/judgments/">SC headnotes</a>
        <a routerLink="/about">About us</a>
        <a routerLink="/help">Help</a>
        <a routerLink="/privacy">Privacy</a>
        <a routerLink="/terms">Terms</a>
        <a routerLink="/trust">Trust &amp; security</a>
        <a [href]="'mailto:' + email">Grievance officer</a>
      </nav>
      <p>© 2026 VidhiSangh. A professional network and knowledge platform; it does not advertise or solicit work for advocates.</p>
      <p>VidhiSangh is developed and managed by <a routerLink="/about">Simson Softwares Private Limited</a>.
        WhatsApp: <a [href]="whatsappLink" target="_blank" rel="noopener">{{ whatsappNumber }}</a></p>
    </footer>
  `,
  styles: [`
    :host { display: block; border-top: 1px solid rgb(var(--vs-line)); background: rgb(var(--vs-surface)); }
    .vs-pf { display: flex; flex-wrap: wrap; align-items: center; gap: 1rem 2rem; padding: 2rem max(1rem, calc((100vw - 1160px) / 2)); color: rgb(var(--vs-text-muted)); font-size: .85rem; }
    a { text-decoration: none; color: rgb(var(--vs-text-muted)); } a:hover { color: rgb(var(--vs-content)); }
    .vs-pf__brand { display: flex; align-items: center; gap: .45rem; color: rgb(var(--vs-content)); font-weight: 700; }
    nav { display: flex; flex-wrap: wrap; gap: 1.25rem; }
    p { flex-basis: 100%; margin: 0; }
  `],
})
export class PublicFooterComponent {
  protected readonly email = CONTACT_EMAIL;
  protected readonly whatsappNumber = WHATSAPP_NUMBER;
  protected readonly whatsappLink = WHATSAPP_LINK;
}

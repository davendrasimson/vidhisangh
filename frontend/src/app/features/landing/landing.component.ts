import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';

interface Feature {
  id: string;
  eyebrow: string;
  title: string;
  text: string;
  points: string[];
  image: string;
  alt: string;
}

/** Google Play listing; the link works once the app is published. */
const PLAY_URL = 'https://play.google.com/store/apps/details?id=com.vidhisangh.app';

/**
 * Public home page for visitors (signed-in members are sent to the app by
 * `landingGuard`). It markets VidhiSangh as a professional network and a
 * knowledge tool — never as a way for advocates to win clients (BCI Rule 36).
 */
import { WHATSAPP_LINK, WHATSAPP_NUMBER } from '@core/contact';

@Component({
  selector: 'app-landing',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    <header class="topbar">
      <a routerLink="/" class="brand" aria-label="VidhiSangh home">
        <img src="/brand-mark.svg?v=3" alt="" width="32" height="32" /><span>VidhiSangh</span>
      </a>
      <nav aria-label="Sections">
        <a href="#network">Network</a>
        <a href="#research">Research</a>
        <a href="/acts/">Bare Acts</a>
        <a href="/judgments/">Judgments</a>
        <a href="#practice">Practice tools</a>
      </nav>
      <div class="auth">
        <a routerLink="/auth/register" class="join">Join now</a>
        <a routerLink="/auth/login" class="signin">Sign in</a>
      </div>
    </header>

    <main>
      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">विधि संघ · the association of law</p>
          <h1>Welcome to India's legal fraternity</h1>
          <p class="lede">The free professional network for advocates, judges, legal researchers, law students, munshis, law firms and corporate legal teams.</p>
          <div class="cta">
            <a routerLink="/auth/register" class="btn primary">Join now — it's free</a>
            <a routerLink="/auth/login" class="btn ghost">Sign in</a>
          </div>
          <a [href]="playUrl" target="_blank" rel="noopener" class="play">
            <mat-icon class="material-icons-outlined">android</mat-icon> Get the Android app on Google Play
          </a>
        </div>
        <div class="hero-shot">
          <div class="phone"><img src="/images/landing/01-feed.webp" alt="Advocates sharing legal updates in the VidhiSangh feed" width="540" height="960" /></div>
        </div>
      </section>

      <section class="who" aria-labelledby="who-title">
        <h2 id="who-title">One home for everyone who works in Indian law</h2>
        <ul class="chips">
          @for (r of roles; track r.label) {
            <li><mat-icon class="material-icons-outlined">{{ r.icon }}</mat-icon>{{ r.label }}</li>
          }
        </ul>
      </section>

      <section class="stats" aria-label="VidhiSangh at a glance">
        <div><strong>5.9 million</strong><span>Supreme Court and High Court judgments and orders</span></div>
        <div><strong>25</strong><span>central Acts, including BNS, BNSS and BSA, readable offline</span></div>
        <div><strong>Free</strong><span>to join and to network with the fraternity</span></div>
      </section>

      @for (f of features; track f.id; let odd = $odd) {
        <section class="feature" [class.flip]="odd" [id]="f.id">
          <div class="feature-copy">
            <p class="eyebrow">{{ f.eyebrow }}</p>
            <h2>{{ f.title }}</h2>
            <p>{{ f.text }}</p>
            <ul>
              @for (p of f.points; track p) {
                <li><mat-icon class="material-icons-outlined">check_circle</mat-icon>{{ p }}</li>
              }
            </ul>
          </div>
          <div class="phone small"><img [src]="f.image" [alt]="f.alt" width="540" height="960" loading="lazy" /></div>
        </section>
      }

      <section class="trust">
        <mat-icon class="material-icons-outlined">verified_user</mat-icon>
        <div>
          <h2>Private by design</h2>
          <p>Your data is encrypted in transit and at rest and handled under the Digital Personal Data Protection Act, 2023. You choose who sees your profile, and you can download your data or delete your account at any time.</p>
        </div>
        <a routerLink="/trust">How we protect your data →</a>
      </section>

      <section class="final">
        <h2>Join your colleagues on VidhiSangh</h2>
        <p>Build your profile in two minutes. Free for every member of the legal fraternity.</p>
        <div class="cta">
          <a routerLink="/auth/register" class="btn primary">Join now — it's free</a>
          <a [href]="playUrl" target="_blank" rel="noopener" class="btn ghost">Get the Android app</a>
        </div>
      </section>
    </main>

    <footer>
      <div class="foot-brand"><img src="/brand-mark.svg?v=3" alt="" width="24" height="24" /> VidhiSangh</div>
      <nav aria-label="Legal and help">
        <a href="/acts/">Bare Acts</a>
        <a href="/judgments/">SC headnotes</a>
        <a routerLink="/about">About us</a>
        <a routerLink="/help">Help</a>
        <a routerLink="/privacy">Privacy</a>
        <a routerLink="/terms">Terms</a>
        <a routerLink="/trust">Trust &amp; security</a>
        <a href="mailto:grievance@vidhisangh.com">Grievance officer</a>
      </nav>
      <p>© 2026 VidhiSangh. A professional network and knowledge platform; it does not advertise or solicit work for advocates.</p>
      <p>VidhiSangh is developed and managed by <a routerLink="/about">Simson Softwares Private Limited</a>.
        WhatsApp: <a [href]="whatsappLink" target="_blank" rel="noopener">{{ whatsappNumber }}</a></p>
    </footer>
  `,
  styles: [`
    :host { display: block; min-height: 100vh; background: rgb(var(--vs-surface)); color: rgb(var(--vs-content)); }
    a { text-decoration: none; }
    .topbar { position: sticky; z-index: 10; inset: 0 0 auto; display: flex; align-items: center; gap: 1.5rem; padding: .75rem max(1rem, calc((100vw - 1160px) / 2)); background: rgb(var(--vs-surface-raised) / .92); backdrop-filter: blur(10px); border-bottom: 1px solid rgb(var(--vs-line)); }
    .brand { display: flex; align-items: center; gap: .55rem; color: rgb(var(--vs-content)); font-family: var(--vs-font-display); font-size: 1.3rem; font-weight: 700; }
    .topbar nav { display: flex; gap: 1.25rem; } .topbar nav a { color: rgb(var(--vs-text-muted)); font-size: .9rem; font-weight: 500; } .topbar nav a:hover { color: rgb(var(--vs-content)); }
    .auth { display: flex; align-items: center; gap: .5rem; margin-left: auto; }
    .join { padding: .7rem 1.4rem; border-radius: 999px; color: #fff; background: linear-gradient(135deg, #215dcc, #4934b8); font-weight: 700; font-size: .98rem; box-shadow: 0 8px 20px -8px rgb(33 93 204 / .7); }
    .join:hover { filter: brightness(1.08); }
    .signin { padding: .62rem 1.3rem; border-radius: 999px; border: 2px solid #215dcc; color: #215dcc; font-weight: 700; font-size: .98rem; }
    .signin:hover { background: rgb(33 93 204 / .08); }
    main { overflow-x: hidden; }
    .hero { display: grid; grid-template-columns: 1.1fr .9fr; align-items: center; gap: 2rem; padding: 4rem max(1rem, calc((100vw - 1160px) / 2)) 3rem; color: #fff; background: linear-gradient(160deg, #173b7a 0%, #215dcc 55%, #4934b8 100%); }
    .eyebrow { margin: 0 0 .75rem; color: #f4c86a; font-size: .8rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
    h1 { margin: 0; font-family: var(--vs-font-display); font-size: clamp(2.3rem, 5vw, 3.9rem); line-height: 1.05; }
    .lede { max-width: 560px; margin: 1.25rem 0 0; color: rgb(255 255 255 / .85); font-size: 1.15rem; line-height: 1.6; }
    .cta { display: flex; flex-wrap: wrap; gap: .75rem; margin-top: 2rem; }
    .btn { display: inline-flex; align-items: center; justify-content: center; min-width: 11rem; padding: 1rem 2rem; border-radius: 999px; font-weight: 700; font-size: 1.1rem; }
    .btn.primary { color: #173b7a; background: #f4c86a; box-shadow: 0 12px 28px -10px rgb(0 0 0 / .45); } .btn.primary:hover { background: #f7d48a; transform: translateY(-1px); }
    .btn.ghost { color: #fff; border: 2px solid #fff; background: rgb(255 255 255 / .08); } .btn.ghost:hover { background: rgb(255 255 255 / .18); }
    .play { display: inline-flex; align-items: center; gap: .4rem; margin-top: 1.25rem; color: rgb(255 255 255 / .85); font-size: .92rem; } .play:hover { color: #fff; text-decoration: underline; }
    .hero-shot { display: flex; justify-content: center; }
    .phone { width: min(300px, 70vw); padding: 10px; border-radius: 36px; background: #0d1530; box-shadow: 0 30px 70px rgb(0 0 0 / .35); }
    .phone img { display: block; width: 100%; height: auto; border-radius: 28px; }
    .phone.small { width: min(260px, 66vw); }
    .who { padding: 3.5rem max(1rem, calc((100vw - 1160px) / 2)) 1rem; text-align: center; }
    .who h2, .final h2 { margin: 0; font-family: var(--vs-font-display); font-size: clamp(1.6rem, 3.2vw, 2.3rem); }
    .chips { display: flex; flex-wrap: wrap; justify-content: center; gap: .6rem; margin: 1.75rem 0 0; padding: 0; list-style: none; }
    .chips li { display: inline-flex; align-items: center; gap: .4rem; padding: .55rem 1rem; border: 1px solid rgb(var(--vs-line)); border-radius: 999px; background: rgb(var(--vs-surface-raised)); font-size: .92rem; font-weight: 500; }
    .chips mat-icon { width: 20px; height: 20px; font-size: 20px; color: #215dcc; }
    .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; width: min(1160px, calc(100% - 2rem)); margin: 2.5rem auto; }
    .stats div { padding: 1.5rem; border-radius: 16px; background: rgb(var(--vs-surface-raised)); border: 1px solid rgb(var(--vs-line)); }
    .stats strong { display: block; font-family: var(--vs-font-display); font-size: 2.2rem; color: #215dcc; } .stats span { color: rgb(var(--vs-text-muted)); line-height: 1.5; }
    .feature { display: grid; grid-template-columns: 1.2fr .8fr; align-items: center; gap: 3rem; width: min(1160px, calc(100% - 2rem)); margin: 0 auto; padding: 3rem 0; border-top: 1px solid rgb(var(--vs-line)); scroll-margin-top: 70px; }
    .feature .phone { justify-self: center; }
    .feature.flip .feature-copy { order: 2; }
    .feature h2 { margin: 0; font-family: var(--vs-font-display); font-size: clamp(1.6rem, 3vw, 2.2rem); line-height: 1.15; }
    .feature .eyebrow { color: #215dcc; }
    .feature p { color: rgb(var(--vs-text-muted)); font-size: 1.05rem; line-height: 1.65; }
    .feature ul { display: grid; gap: .6rem; margin: 1.25rem 0 0; padding: 0; list-style: none; }
    .feature li { display: flex; gap: .55rem; align-items: flex-start; line-height: 1.45; }
    .feature li mat-icon { flex: none; width: 20px; height: 20px; font-size: 20px; color: rgb(var(--vs-success)); }
    .trust { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 1.25rem; width: min(1160px, calc(100% - 2rem)); margin: 2rem auto; padding: 1.5rem; border-radius: 16px; background: rgb(var(--vs-surface-sunken)); border: 1px solid rgb(var(--vs-line)); }
    .trust > mat-icon { width: 36px; height: 36px; font-size: 36px; color: rgb(var(--vs-success)); }
    .trust h2 { margin: 0; font-size: 1.2rem; } .trust p { margin: .3rem 0 0; color: rgb(var(--vs-text-muted)); line-height: 1.55; } .trust a { color: #215dcc; font-weight: 600; white-space: nowrap; }
    .final { margin-top: 3rem; padding: 4rem 1rem; text-align: center; color: #fff; background: linear-gradient(160deg, #173b7a 0%, #215dcc 55%, #4934b8 100%); }
    .final p { margin: .9rem 0 0; color: rgb(255 255 255 / .85); font-size: 1.1rem; } .final .cta { justify-content: center; }
    footer { display: flex; flex-wrap: wrap; align-items: center; gap: 1rem 2rem; padding: 2rem max(1rem, calc((100vw - 1160px) / 2)); color: rgb(var(--vs-text-muted)); font-size: .85rem; }
    .foot-brand { display: flex; align-items: center; gap: .45rem; color: rgb(var(--vs-content)); font-weight: 700; }
    footer nav { display: flex; flex-wrap: wrap; gap: 1.25rem; } footer nav a { color: rgb(var(--vs-text-muted)); } footer nav a:hover { color: rgb(var(--vs-content)); }
    footer p { flex-basis: 100%; margin: 0; }
    @media (max-width: 860px) {
      .topbar { gap: .75rem; } .topbar nav { display: none; }
      .brand span { font-size: 1.1rem; }
      .join { padding: .55rem 1rem; font-size: .9rem; } .signin { padding: .48rem .95rem; font-size: .9rem; }
      .cta .btn { flex: 1 1 100%; }
      .hero { grid-template-columns: 1fr; padding-top: 2.5rem; text-align: left; }
      .stats { grid-template-columns: 1fr; }
      .feature { grid-template-columns: 1fr; gap: 1.5rem; } .feature.flip .feature-copy { order: 0; }
      .trust { grid-template-columns: 1fr; }
    }
  `],
})
export class LandingComponent {
  protected readonly whatsappNumber = WHATSAPP_NUMBER;
  protected readonly whatsappLink = WHATSAPP_LINK;
  protected readonly playUrl = PLAY_URL;

  protected readonly roles = [
    { icon: 'gavel', label: 'Advocates and Senior Advocates' },
    { icon: 'account_balance', label: 'Judicial officers' },
    { icon: 'menu_book', label: 'Legal researchers and academics' },
    { icon: 'school', label: 'Law students' },
    { icon: 'badge', label: 'Munshis and court clerks' },
    { icon: 'apartment', label: 'Law firms and chambers' },
    { icon: 'business_center', label: 'Corporate legal teams' },
    { icon: 'handshake', label: 'Arbitrators and mediators' },
  ];

  protected readonly features: Feature[] = [
    {
      id: 'network', eyebrow: 'Professional network', title: 'Connect with the fraternity across India',
      text: 'A profile made for Indian law — Bar Council, enrolment, courts of practice and areas of law — and a trusted network of seniors, peers and juniors.',
      points: ['Verified professional profiles', 'Connections, follows and a feed of legal updates', 'Private messaging in real time'],
      image: '/images/landing/03-people.webp', alt: 'Connection requests and advocates to connect with',
    },
    {
      id: 'communities', eyebrow: 'Communities', title: 'Communities for every court and practice',
      text: 'Discuss arbitration, criminal law, service matters or life at the Bar with people who practise it.',
      points: ['Communities by practice area, court, bar association or law school', 'Firm pages and moderated private groups', 'Hashtags such as #BNSS and #Arbitration'],
      image: '/images/landing/04-groups.webp', alt: 'Legal communities for arbitration, criminal law and young advocates',
    },
    {
      id: 'research', eyebrow: 'Legal research', title: '5.9 million judgments, one search',
      text: 'Search Supreme Court and High Court judgments and orders with parties, counsel, bench and the full case history.',
      points: ['Exact phrases, exclusions and case numbers', 'Every order in a case on one page', 'Save, compare and set alerts'],
      image: '/images/landing/07-research.webp', alt: 'Searching Supreme Court and High Court judgments',
    },
    {
      id: 'bare-acts', eyebrow: 'Bare Acts', title: 'BNS, BNSS, BSA — clear and offline',
      text: 'Read the new criminal laws and other central Acts as clear, searchable text on your phone, even without a connection.',
      points: ['25 central Acts', 'Search within an Act by section or phrase', 'Read BNS, BNSS and BSA section by section at vidhisangh.com/acts'],
      image: '/images/landing/09-bareact.webp', alt: 'Reading the Bharatiya Nyaya Sanhita 2023 as clear text',
    },
    {
      id: 'local-counsel', eyebrow: 'Collaboration', title: 'Find local counsel in another city',
      text: 'Post a request for counsel before another court or bench and hear back from professionals there. Also internships and jobs.',
      points: ['Local counsel, experts and researchers', 'Internships and jobs for the fraternity', 'No referral fees — work, not commissions'],
      image: '/images/landing/06-marketplace.webp', alt: 'Requests for local counsel and referrals',
    },
    {
      id: 'practice', eyebrow: 'Practice tools (optional)', title: 'Run your practice in the same app',
      text: 'When you need them: matters, hearings, clients, drafting and GST invoices for chambers and firms.',
      points: ['Matters with next hearings and fee arrangements', 'Drafting in English, Hindi and Punjabi', 'Time entries and GST invoices'],
      image: '/images/landing/12-matters.webp', alt: 'Tracking cases and next hearing dates',
    },
  ];
}

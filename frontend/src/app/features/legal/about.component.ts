import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { WHATSAPP_LINK, WHATSAPP_NUMBER } from '@core/contact';

@Component({
  selector: 'app-about',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <div class="page">
      <header class="topbar">
        <a routerLink="/" class="brand"><img src="/brand-mark.svg?v=3" alt="" width="30" height="30" />VidhiSangh</a>
        <nav><a routerLink="/help">Help</a><a routerLink="/privacy">Privacy</a><a routerLink="/auth/login">Sign in</a></nav>
      </header>

      <main>
        <p class="eyebrow">About us</p>
        <h1>VidhiSangh — विधि संघ, the association of law</h1>
        <p class="lede">VidhiSangh is a free professional network for India's legal fraternity, with legal research and
          practice tools built in. One place for advocates, judges, legal researchers, law teachers, law students,
          munshis, law firms and in-house legal teams to connect, learn and work.</p>

        <section>
          <h2>What VidhiSangh offers</h2>
          <ul>
            <li><strong>A professional network.</strong> Profiles made for law, connections, a feed, communities,
              private messaging, and requests for referrals and local counsel.</li>
            <li><strong>Legal knowledge.</strong> Search of Supreme Court and High Court judgments and orders,
              AI-generated headnotes of Supreme Court judgments (always marked as AI-generated), and the BNS, BNSS, BSA
              and other central Acts as searchable text.</li>
            <li><strong>Practice tools, when you need them.</strong> Matters and hearings, clients and KYC, drafting
              in English, Hindi and Punjabi, e-signatures, time entries and GST invoices.</li>
          </ul>
          <p>VidhiSangh does not advertise or solicit work for advocates.</p>
        </section>

        <section class="company">
          <h2>Who builds it</h2>
          <p><strong>VidhiSangh is developed and managed by Simson Softwares Private Limited.</strong> Simson Softwares
            builds and runs the platform, its website and its Android and iOS apps, and is responsible for the
            service and the data it holds, as described in the <a routerLink="/privacy">privacy notice</a> and
            <a routerLink="/terms">terms of service</a>.</p>
        </section>

        <section>
          <h2>Contact</h2>
          <p>WhatsApp: <a [href]="whatsappLink" target="_blank" rel="noopener">{{ whatsappNumber }}</a></p>
          <p>Questions, complaints and data requests: <a href="mailto:grievance@vidhisangh.com">grievance@vidhisangh.com</a>.
            For help using the product, see the <a routerLink="/help">help centre</a>. Our security and privacy
            controls are summarised on the <a routerLink="/trust">trust page</a>.</p>
        </section>

        <p class="actions"><a routerLink="/auth/register" class="join">Join VidhiSangh free</a></p>
      </main>
    </div>
  `,
  styles: [`
    :host { display: block; min-height: 100vh; background: rgb(var(--vs-surface)); color: rgb(var(--vs-content)); }
    .topbar { display: flex; align-items: center; gap: 1rem; padding: 1rem max(1.25rem, calc((100vw - 860px)/2)); background: rgb(var(--vs-surface-raised)); border-bottom: 1px solid rgb(var(--vs-line)); }
    .brand { display: flex; align-items: center; gap: .5rem; color: rgb(var(--vs-content)); font-family: var(--vs-font-display); font-size: 1.25rem; font-weight: 700; text-decoration: none; }
    nav { display: flex; gap: 1rem; margin-left: auto; } nav a { color: rgb(var(--vs-text-muted)); text-decoration: none; font-size: .92rem; }
    main { width: min(860px, calc(100% - 2rem)); margin: 0 auto; padding: 3rem 0 4rem; line-height: 1.7; }
    .eyebrow { margin: 0 0 .5rem; color: rgb(var(--vs-brand)); font-size: .75rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: 0; font-family: var(--vs-font-display); font-size: clamp(2rem, 5vw, 3rem); line-height: 1.1; }
    .lede { margin: 1.25rem 0 0; color: rgb(var(--vs-text-muted)); font-size: 1.1rem; }
    section { margin-top: 2.25rem; } h2 { margin: 0 0 .6rem; font-size: 1.3rem; }
    ul { margin: 0; padding-left: 1.2rem; } li { margin-bottom: .6rem; }
    a { color: rgb(var(--vs-brand)); }
    .company { padding: 1.25rem 1.5rem; border-radius: 16px; border: 1px solid rgb(var(--vs-line)); background: rgb(var(--vs-surface-raised)); }
    .company p { margin: 0; }
    .actions { margin-top: 2.5rem; }
    .join { display: inline-block; padding: .75rem 1.4rem; border-radius: 999px; color: #fff; background: linear-gradient(135deg, #215dcc, #4934b8); font-weight: 700; text-decoration: none; }
    @media (max-width: 600px) { nav a:not(:last-child) { display: none; } }
  `],
})
export class AboutComponent {
  protected readonly whatsappNumber = WHATSAPP_NUMBER;
  protected readonly whatsappLink = WHATSAPP_LINK;
}

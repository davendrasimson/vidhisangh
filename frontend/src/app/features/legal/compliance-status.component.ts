import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';

interface FrameworkStatus {
  name: string;
  scope: string;
  status: string;
  tone: 'complete' | 'aligned';
  detail: string;
}

@Component({
  selector: 'app-compliance-status',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    <div class="page">
      <header class="topbar">
        <a routerLink="/" class="brand">VidhiSangh</a>
        <nav><a routerLink="/privacy">Privacy</a><a routerLink="/terms">Terms</a><a routerLink="/auth/login">Sign in</a></nav>
      </header>

      <main>
        <section class="hero">
          <div>
            <p class="eyebrow">Trust &amp; compliance</p>
            <h1>Security controls you can verify.</h1>
            <p class="lede">VidhiSangh completed a code, configuration and production-host review against 65 security and privacy findings on 27 September 2026.</p>
          </div>
          <div class="score" aria-label="65 of 65 assessed findings remediated">
            <strong>65/65</strong><span>assessed findings<br>remediated</span>
          </div>
        </section>

        <section class="summary" aria-label="Current review status">
          <mat-icon class="material-icons-outlined">verified_user</mat-icon>
          <div><strong>All assessed application controls are implemented.</strong><p>Evidence is maintained in the repository controls matrix and backed by automated tests, audit trails and production configuration checks.</p></div>
          <span>Reviewed 27/09/2026</span>
        </section>

        <section class="frameworks">
          @for (item of frameworks; track item.name) {
            <article>
              <div class="card-head"><span class="mark"><mat-icon class="material-icons-outlined">{{ item.tone === 'complete' ? 'check_circle' : 'fact_check' }}</mat-icon></span><span class="status {{ item.tone }}">{{ item.status }}</span></div>
              <h2>{{ item.name }}</h2>
              <p class="scope">{{ item.scope }}</p>
              <p>{{ item.detail }}</p>
            </article>
          }
        </section>

        <section class="controls">
          <div>
            <p class="eyebrow">Controls in operation</p>
            <h2>Protection across the full application</h2>
            <p>These controls apply across identity, matters, documents, research, billing, client portals and integrations.</p>
          </div>
          <ul>
            @for (control of controls; track control) { <li><mat-icon class="material-icons-outlined">check</mat-icon>{{ control }}</li> }
          </ul>
        </section>

        <aside class="disclosure">
          <mat-icon class="material-icons-outlined">info</mat-icon>
          <p><strong>About this status.</strong> “Implemented” means the assessed technical control exists and was reviewed. ISO/IEC certification is granted only by an accredited certification body. Formal ISMS/PIMS certification, an independent penetration test, production-volume KMS encryption, independent secondary DNS and legal review remain operational governance activities. Salil Shaida is the published Grievance Officer; encrypted off-host recovery is tested separately and dated in the controls record.</p>
        </aside>

        <div class="actions"><a routerLink="/privacy">Read the Privacy Notice</a><a routerLink="/terms">Read the Terms</a><a routerLink="/auth/login" class="primary">Open VidhiSangh</a></div>
      </main>
    </div>
  `,
  styles: [`
    :host { display: block; min-height: 100vh; background: rgb(var(--vs-surface-sunken)); color: rgb(var(--vs-content)); }
    .topbar { display: flex; align-items: center; gap: 1rem; padding: 1rem max(1.25rem, calc((100vw - 1120px)/2)); background: rgb(var(--vs-surface-raised)); border-bottom: 1px solid rgb(var(--vs-line)); }
    .brand { color: rgb(var(--vs-content)); font-family: var(--vs-font-display); font-size: 1.25rem; font-weight: 700; text-decoration: none; }
    nav { display: flex; gap: 1.25rem; margin-left: auto; } nav a { color: rgb(var(--vs-text-muted)); font-size: .88rem; text-decoration: none; }
    main { width: min(1120px, calc(100% - 2rem)); margin: 0 auto; padding: 3.5rem 0 4rem; }
    .hero { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 2rem; padding: clamp(2rem, 5vw, 4rem); border-radius: 24px; overflow: hidden; color: #fff; background: radial-gradient(circle at 85% 15%, rgb(36 180 126 / .38), transparent 33%), linear-gradient(145deg, #111d3c, #173d67 58%, #135b55); box-shadow: 0 20px 60px rgb(16 30 65 / .2); }
    .eyebrow { margin: 0 0 .65rem; color: #80e8bf; font-size: .75rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
    h1 { max-width: 700px; margin: 0; font-family: var(--vs-font-display); font-size: clamp(2.25rem, 5vw, 4.2rem); line-height: 1.02; }
    .lede { max-width: 720px; margin: 1.25rem 0 0; color: rgb(255 255 255 / .78); font-size: 1.05rem; line-height: 1.65; }
    .score { min-width: 180px; padding: 1.5rem; border: 1px solid rgb(255 255 255 / .25); border-radius: 18px; background: rgb(255 255 255 / .1); backdrop-filter: blur(8px); text-align: center; }
    .score strong { display: block; font-size: 2.5rem; line-height: 1; } .score span { display: block; margin-top: .6rem; color: rgb(255 255 255 / .72); font-size: .82rem; line-height: 1.35; }
    .summary { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 1rem; margin: 1.25rem 0 2rem; padding: 1rem 1.25rem; border: 1px solid color-mix(in srgb, rgb(var(--vs-success)) 35%, rgb(var(--vs-line))); border-radius: 14px; background: color-mix(in srgb, rgb(var(--vs-success)) 8%, rgb(var(--vs-surface-raised))); }
    .summary > mat-icon { color: rgb(var(--vs-success)); } .summary p { margin: .2rem 0 0; color: rgb(var(--vs-text-muted)); font-size: .85rem; } .summary > span { color: rgb(var(--vs-text-muted)); font-size: .78rem; }
    .frameworks { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }
    article { padding: 1.5rem; border: 1px solid rgb(var(--vs-line)); border-radius: 16px; background: rgb(var(--vs-surface-raised)); box-shadow: var(--vs-shadow-card); }
    .card-head { display: flex; align-items: center; justify-content: space-between; } .mark { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 12px; color: rgb(var(--vs-brand)); background: color-mix(in srgb, rgb(var(--vs-brand)) 11%, transparent); }
    .status { padding: .3rem .55rem; border-radius: 999px; font-size: .7rem; font-weight: 700; } .status.complete { color: #08764c; background: #d9f7e9; } .status.aligned { color: #8a5b00; background: #fff0c2; }
    article h2 { margin: 1rem 0 .2rem; font-size: 1.2rem; } article p { color: rgb(var(--vs-text-muted)); line-height: 1.55; } article .scope { margin: 0 0 .8rem; color: rgb(var(--vs-brand)); font-size: .78rem; font-weight: 700; }
    .controls { display: grid; grid-template-columns: .8fr 1.2fr; gap: 3rem; margin-top: 2rem; padding: 2rem; border-radius: 18px; background: rgb(var(--vs-surface-raised)); border: 1px solid rgb(var(--vs-line)); }
    .controls .eyebrow { color: rgb(var(--vs-brand)); } .controls h2 { margin: 0; font-size: 1.7rem; } .controls p { color: rgb(var(--vs-text-muted)); line-height: 1.6; }
    ul { display: grid; grid-template-columns: repeat(2, 1fr); gap: .8rem; margin: 0; padding: 0; list-style: none; } li { display: flex; gap: .55rem; align-items: flex-start; font-size: .88rem; } li mat-icon { flex: none; width: 18px; height: 18px; color: rgb(var(--vs-success)); font-size: 18px; }
    .disclosure { display: flex; gap: .8rem; margin-top: 1rem; padding: 1rem 1.2rem; border-radius: 12px; color: rgb(var(--vs-text-muted)); background: color-mix(in srgb, rgb(var(--vs-warning)) 8%, transparent); border: 1px solid color-mix(in srgb, rgb(var(--vs-warning)) 28%, rgb(var(--vs-line))); font-size: .82rem; line-height: 1.55; } .disclosure p { margin: 0; } .disclosure mat-icon { flex: none; color: rgb(var(--vs-warning)); }
    .actions { display: flex; justify-content: flex-end; align-items: center; gap: 1rem; margin-top: 1.5rem; } .actions a { color: rgb(var(--vs-brand)); font-weight: 600; text-decoration: none; } .actions .primary { padding: .7rem 1rem; border-radius: 10px; color: #fff; background: rgb(var(--vs-brand)); }
    @media (max-width: 760px) { nav a:not(:last-child) { display: none; } .hero { grid-template-columns: 1fr; } .score { width: 100%; } .summary { grid-template-columns: auto 1fr; } .summary > span { grid-column: 2; } .frameworks, .controls { grid-template-columns: 1fr; } .controls { gap: 1rem; } ul { grid-template-columns: 1fr; } .actions { flex-wrap: wrap; justify-content: flex-start; } }
  `],
})
export class ComplianceStatusComponent {
  protected readonly frameworks: FrameworkStatus[] = [
    { name: 'OWASP Top 10', scope: 'Application security review', status: 'Assessed controls implemented', tone: 'complete', detail: 'Access control, cryptography, injection resistance, secure configuration, authentication, integrity, logging and SSRF controls were reviewed and remediated.' },
    { name: 'DPDP Act 2023', scope: 'Technical privacy controls', status: 'Controls implemented', tone: 'complete', detail: 'Versioned notice and consent, data rights, grievance workflow, retention, erasure, encryption and privacy-event records are built into the product.' },
    { name: 'ISMS · ISO/IEC 27001', scope: 'Information security management', status: 'Control-aligned', tone: 'aligned', detail: 'Application and infrastructure controls map to Annex A. Formal certification and the organisation-level policy programme remain separate governance work.' },
    { name: 'PIMS · ISO/IEC 27701', scope: 'Privacy information management', status: 'Control-aligned', tone: 'aligned', detail: 'Privacy controls map to controller and processor responsibilities. Certification, counsel review and operating evidence require an independent programme.' },
  ];

  protected readonly controls = [
    'Tenant isolation with forced PostgreSQL row-level security',
    'Encrypted identity data and blind-index search',
    'HttpOnly refresh sessions, MFA, passkeys and lockout',
    'Append-only, hash-chained security audit records',
    'Consent, access, correction, erasure and grievance workflows',
    'Upload validation, SSRF protection and signed webhooks',
    'Secure headers, CSP, rate limits and secret validation',
    'Automated retention, encrypted backups and restore tooling',
  ];
}

import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

/**
 * Split-screen marketing / form layout for unauthenticated pages.
 *
 * The brand side draws on the visual language of the Indian courts: the deep
 * indigo of a judge's robe over the ochre of the sandstone our High Courts are
 * built from, behind a jaali (lattice) screen of the kind cut into their
 * facades. The motto is the national one, सत्यमेव जयते. We deliberately do NOT
 * reproduce the State Emblem — its use is restricted by the State Emblem of
 * India (Prohibition of Improper Use) Act, 2005.
 */
@Component({
  selector: 'app-auth-layout',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink],
  template: `
    <div class="auth">
      <aside class="auth__brand">
        <svg class="auth__jaali" aria-hidden="true" focusable="false">
          <defs>
            <pattern id="vs-jaali" width="64" height="64" patternUnits="userSpaceOnUse">
              <path d="M32 0 64 32 32 64 0 32Z" fill="none" stroke="currentColor" stroke-width="1" />
              <circle cx="32" cy="32" r="13.5" fill="none" stroke="currentColor" stroke-width="1" />
              <path
                d="M0 0l13 13M64 0L51 13M0 64l13-13M64 64l-13-13"
                fill="none"
                stroke="currentColor"
                stroke-width="1"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#vs-jaali)" />
        </svg>

        <div class="auth__brand-inner">
          <div class="auth__logo">
            <img class="auth__mark" src="brand-mark.svg" alt="" width="42" height="42" />
            <span class="auth__wordmark">VidhiSangh</span>
          </div>

          <div class="auth__motto">
            <p class="auth__motto-sa vs-devanagari" lang="sa">सत्यमेव जयते</p>
            <p class="auth__motto-en">Truth alone triumphs</p>
          </div>

          <h1 class="vs-display">
            Built for the practice of law
            <span>in India.</span>
          </h1>

          <p class="auth__lede">
            From the district courts to the Supreme Court — research, matters,
            filings and billing in one secure, multi-tenant platform for
            advocates, chambers and in-house teams.
          </p>

          <ul class="auth__features">
            <li>Bar Council&ndash;verified advocate network</li>
            <li>Judgments &amp; citations, searched in plain language</li>
            <li>Cause lists, hearings, matters &amp; billing</li>
            <li>Data held in India &middot; encrypted and audited</li>
          </ul>

          <p class="auth__courts">
            Supreme Court &middot; High Courts &middot; District Judiciary &middot; Tribunals
          </p>
          <a routerLink="/trust" class="auth__trust">Verified security &amp; privacy status →</a>
        </div>
      </aside>

      <section class="auth__panel">
        <div class="auth__panel-inner">
          <div class="auth__mobile-brand" aria-hidden="true">
            <img class="auth__mark" src="brand-mark.svg" alt="" width="34" height="34" />
            <span class="auth__wordmark">VidhiSangh</span>
          </div>
          <router-outlet />
        </div>
      </section>
    </div>
  `,
  styles: [
    `
      .auth {
        display: grid;
        grid-template-columns: 1.05fr 1fr;
        min-height: 100vh;
      }

      /* ── Brand side ─────────────────────────────────────────────── */
      .auth__brand {
        position: relative;
        isolation: isolate;
        overflow: hidden;
        display: grid;
        place-items: center;
        padding: 3.5rem 3rem;
        color: #fff;
        background:
          radial-gradient(120% 90% at 12% 8%, rgb(30 58 138 / 0.85) 0%, transparent 58%),
          radial-gradient(95% 80% at 88% 96%, rgb(var(--vs-sandstone) / 0.5) 0%, transparent 62%),
          linear-gradient(158deg, #101d3d 0%, #17306a 46%, #241d4f 100%);
      }

      /* The jaali screen — carried on currentColor so it stays a whisper. */
      .auth__jaali {
        position: absolute;
        inset: -10%;
        width: 120%;
        height: 120%;
        z-index: -1;
        color: #fff;
        opacity: 0.075;
        transform: rotate(-8deg);
      }

      /* A gold rule along the inner edge, like tooling on a case binding. */
      .auth__brand::after {
        content: '';
        position: absolute;
        inset-block: 0;
        inset-inline-end: 0;
        width: 1px;
        background: linear-gradient(
          to bottom,
          transparent,
          rgb(var(--vs-gold) / 0.55) 22%,
          rgb(var(--vs-gold) / 0.55) 78%,
          transparent
        );
      }

      .auth__brand-inner {
        max-width: 30rem;
      }

      .auth__logo {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        color: rgb(var(--vs-gold));
      }

      .auth__mark {
        width: 2.625rem;
        height: 2.625rem;
        flex: none;
        filter: drop-shadow(0 8px 16px rgb(0 0 0 / 0.2));
      }

      .auth__wordmark {
        font-family: var(--vs-font-display);
        font-size: 1.6rem;
        font-weight: 600;
        letter-spacing: 0.005em;
        color: #fff;
      }

      .auth__trust {
        display: inline-block;
        margin-top: 1rem;
        color: rgb(255 255 255 / 0.8);
        font-size: 0.78rem;
        font-weight: 600;
        text-decoration: none;
      }
      .auth__trust:hover { color: #fff; text-decoration: underline; }

      .auth__motto {
        margin-top: 2.25rem;
        padding-inline-start: 1rem;
        border-inline-start: 2px solid rgb(var(--vs-gold) / 0.75);
      }

      .auth__motto-sa {
        margin: 0;
        font-size: 1.35rem;
        color: rgb(var(--vs-gold));
      }

      .auth__motto-en {
        margin: 0.15rem 0 0;
        font-size: 0.8rem;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: rgb(255 255 255 / 0.62);
      }

      .auth__brand h1 {
        margin: 1.75rem 0 0;
        font-size: clamp(2rem, 3.1vw, 2.9rem);
        font-weight: 600;
        line-height: 1.15;
        /* Even line lengths instead of a single orphaned word. */
        text-wrap: balance;
      }

      .auth__brand h1 span {
        display: block;
        color: rgb(var(--vs-gold));
      }

      .auth__lede {
        margin-top: 1.15rem;
        max-width: 27rem;
        line-height: 1.65;
        color: rgb(255 255 255 / 0.8);
      }

      .auth__features {
        margin: 2rem 0 0;
        padding: 0;
        list-style: none;
        display: grid;
        gap: 0.7rem;
        font-size: 0.95rem;
        color: rgb(255 255 255 / 0.92);
      }

      .auth__features li {
        display: grid;
        grid-template-columns: 1.1rem 1fr;
        gap: 0.7rem;
        align-items: start;
      }

      /* Tick drawn in CSS so it needs no icon font to render. */
      .auth__features li::before {
        content: '';
        margin-top: 0.34rem;
        width: 0.62rem;
        height: 0.34rem;
        border-inline-start: 2px solid rgb(var(--vs-gold));
        border-block-end: 2px solid rgb(var(--vs-gold));
        transform: rotate(-45deg);
      }

      .auth__courts {
        margin: 2.5rem 0 0;
        padding-top: 1.25rem;
        border-top: 1px solid rgb(255 255 255 / 0.14);
        font-size: 0.72rem;
        letter-spacing: 0.085em;
        text-transform: uppercase;
        color: rgb(255 255 255 / 0.55);
        text-wrap: balance;
      }

      /* ── Form side ──────────────────────────────────────────────── */
      .auth__panel {
        display: grid;
        place-items: center;
        padding: 2rem;
        background: rgb(var(--vs-surface-sunken));
      }

      /* Sized for the widest child (registration); login fills the same
         column so both pages align with the brand bar above them. */
      .auth__panel-inner {
        width: 100%;
        max-width: 27rem;
      }

      .auth__mobile-brand {
        display: none;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 2rem;
        color: rgb(var(--vs-brand));
      }

      .auth__mobile-brand .auth__mark {
        width: 1.75rem;
        height: 1.75rem;
      }

      .auth__mobile-brand .auth__wordmark {
        font-size: 1.3rem;
        color: rgb(var(--vs-text));
      }

      @media (max-width: 900px) {
        .auth {
          grid-template-columns: 1fr;
        }
        .auth__brand {
          display: none;
        }
        .auth__mobile-brand {
          display: flex;
        }
      }

      @media (prefers-reduced-motion: no-preference) {
        .auth__brand-inner > * {
          animation: auth-rise 0.5s cubic-bezier(0.22, 1, 0.36, 1) backwards;
        }
        .auth__motto {
          animation-delay: 0.05s;
        }
        .auth__brand h1 {
          animation-delay: 0.1s;
        }
        .auth__lede {
          animation-delay: 0.15s;
        }
        .auth__features {
          animation-delay: 0.2s;
        }
        .auth__courts {
          animation-delay: 0.25s;
        }
      }

      @keyframes auth-rise {
        from {
          opacity: 0;
          transform: translateY(0.6rem);
        }
      }
    `,
  ],
})
export class AuthLayoutComponent {}

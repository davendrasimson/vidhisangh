import { Injectable, effect, signal } from '@angular/core';
import { HI } from './hi';

/** Interface languages. English is the source; Hindi is looked up string by string. */
export type UiLanguage = 'en' | 'hi';

/** Shared with the static bare-act pages (`scripts/build-act-pages.mjs`), so the
 *  choice carries between them and the app on the same origin. */
export const UI_LANGUAGE_KEY = 'vs.lang';

const BROWSER = typeof window !== 'undefined' && typeof localStorage !== 'undefined';

function stored(): UiLanguage {
  if (!BROWSER) return 'en';
  try { return localStorage.getItem(UI_LANGUAGE_KEY) === 'hi' ? 'hi' : 'en'; } catch { return 'en'; }
}

/**
 * The interface language (30 Oct 2026): English or Hindi, chosen on the
 * sign-up page, in the top bar or under Settings → Appearance, kept on this
 * device. Screens opt in by piping their strings through `| t` (the
 * `TPipe`): an English string is the key, `hi.ts` holds the Hindi, and a
 * string without a Hindi entry stays English. Started with sign-up, the
 * diary and the bare-act reader; other screens follow as they are translated.
 */
@Injectable({ providedIn: 'root' })
export class UiLanguageService {
  readonly lang = signal<UiLanguage>(stored());
  readonly isHindi = () => this.lang() === 'hi';

  constructor() {
    effect(() => {
      const lang = this.lang();
      if (!BROWSER) return;
      try { localStorage.setItem(UI_LANGUAGE_KEY, lang); } catch { /* private mode */ }
      document.documentElement.lang = lang === 'hi' ? 'hi-IN' : 'en-IN';
    });
  }

  set(lang: UiLanguage): void { this.lang.set(lang); }
  toggle(): void { this.lang.set(this.lang() === 'hi' ? 'en' : 'hi'); }

  /** The string in the current language (English when no Hindi is recorded). */
  t(text: string): string {
    return this.lang() === 'hi' ? (HI[text] ?? text) : text;
  }
}

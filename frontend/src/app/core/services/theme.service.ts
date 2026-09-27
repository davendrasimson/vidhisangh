import { Injectable, effect, signal } from '@angular/core';

type ThemeMode = 'light' | 'dark' | 'system';
export type Accent =
  | 'blue'
  | 'indigo'
  | 'violet'
  | 'teal'
  | 'emerald'
  | 'rose'
  | 'amber'
  | 'slate';

const STORAGE_KEY = 'vs.theme';
const ACCENT_KEY = 'vs.accent';

/** Brand colour presets. Each carries a light + dark variant (`[brand, brand-fg]`
 *  RGB triplets) so contrast stays right in both themes. `swatch` drives the UI. */
interface AccentDef {
  label: string;
  swatch: string;
  light: [string, string];
  dark: [string, string];
}

export const ACCENTS: Record<Accent, AccentDef> = {
  blue: { label: 'Blue', swatch: '#2563eb', light: ['37 99 235', '255 255 255'], dark: ['96 165 250', '15 23 42'] },
  indigo: { label: 'Indigo', swatch: '#4f46e5', light: ['79 70 229', '255 255 255'], dark: ['129 140 248', '15 23 42'] },
  violet: { label: 'Violet', swatch: '#7c3aed', light: ['124 58 237', '255 255 255'], dark: ['167 139 250', '15 23 42'] },
  teal: { label: 'Teal', swatch: '#0d9488', light: ['13 148 136', '255 255 255'], dark: ['45 212 191', '15 23 42'] },
  emerald: { label: 'Emerald', swatch: '#059669', light: ['5 150 105', '255 255 255'], dark: ['52 211 153', '15 23 42'] },
  rose: { label: 'Rose', swatch: '#e11d48', light: ['225 29 72', '255 255 255'], dark: ['251 113 133', '15 23 42'] },
  amber: { label: 'Amber', swatch: '#d97706', light: ['217 119 6', '255 255 255'], dark: ['251 191 36', '15 23 42'] },
  slate: { label: 'Slate', swatch: '#334155', light: ['51 65 85', '255 255 255'], dark: ['148 163 184', '15 23 42'] },
};

/**
 * Theme controller. Persists the user's light/dark choice (reflected as a `.dark`
 * class on <html>, which flips the design tokens in styles.scss) AND their chosen
 * brand accent (applied as inline `--vs-brand` / `--vs-brand-fg` overrides).
 * 'system' follows the OS preference reactively.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly mode = signal<ThemeMode>(this.initialMode());
  readonly accent = signal<Accent>(this.initialAccent());
  private readonly media = window.matchMedia('(prefers-color-scheme: dark)');

  /** Ordered list for building the colour picker. */
  readonly accentList = (Object.keys(ACCENTS) as Accent[]).map((key) => ({ key, ...ACCENTS[key] }));

  constructor() {
    this.media.addEventListener('change', () => {
      if (this.mode() === 'system') this.apply();
    });
    effect(() => {
      // Re-run whenever mode OR accent changes.
      this.mode();
      this.accent();
      this.apply();
    });
  }

  set(mode: ThemeMode): void {
    this.mode.set(mode);
    localStorage.setItem(STORAGE_KEY, mode);
  }

  toggle(): void {
    this.set(this.isDark() ? 'light' : 'dark');
  }

  setAccent(accent: Accent): void {
    this.accent.set(accent);
    localStorage.setItem(ACCENT_KEY, accent);
  }

  isDark(): boolean {
    const mode = this.mode();
    return mode === 'dark' || (mode === 'system' && this.media.matches);
  }

  private apply(): void {
    const dark = this.isDark();
    document.documentElement.classList.toggle('dark', dark);
    const def = ACCENTS[this.accent()] ?? ACCENTS.blue;
    const [brand, brandFg] = dark ? def.dark : def.light;
    const root = document.documentElement.style;
    root.setProperty('--vs-brand', brand);
    root.setProperty('--vs-brand-fg', brandFg);
  }

  private initialMode(): ThemeMode {
    return (localStorage.getItem(STORAGE_KEY) as ThemeMode) || 'system';
  }

  private initialAccent(): Accent {
    const saved = localStorage.getItem(ACCENT_KEY) as Accent | null;
    return saved && saved in ACCENTS ? saved : 'blue';
  }
}

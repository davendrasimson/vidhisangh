import { Injectable, effect, signal } from '@angular/core';

type ThemeMode = 'light' | 'dark' | 'system';
export type Accent =
  | 'amber'
  | 'navy'
  | 'burgundy'
  | 'forest'
  | 'ocean'
  | 'terracotta'
  | 'plum'
  | 'blue'
  | 'indigo'
  | 'violet'
  | 'teal'
  | 'emerald'
  | 'rose'
  | 'slate';

const STORAGE_KEY = 'vs.theme';
const ACCENT_KEY = 'vs.accent';

/** Brand colour presets. Each carries a light + dark variant (`[brand, brand-fg]`
 *  RGB triplets) so contrast stays right in both themes. `swatch` drives the UI. */
interface AccentDef {
  label: string;
  swatch: string;
  description: string;
  light: [brand: string, foreground: string, companion: string];
  dark: [brand: string, foreground: string, companion: string];
}

export const ACCENTS: Record<Accent, AccentDef> = {
  amber: { label: 'Court Amber', swatch: '#b45309', description: 'Warm and authoritative', light: ['180 83 9', '255 255 255', '120 53 15'], dark: ['251 191 36', '15 23 42', '217 119 6'] },
  navy: { label: 'Advocate Navy', swatch: '#1e3a8a', description: 'Traditional and formal', light: ['30 58 138', '255 255 255', '30 64 175'], dark: ['147 197 253', '15 23 42', '96 165 250'] },
  burgundy: { label: 'Burgundy', swatch: '#9f1239', description: 'Distinguished and confident', light: ['159 18 57', '255 255 255', '127 29 29'], dark: ['253 164 175', '15 23 42', '251 113 133'] },
  forest: { label: 'Forest', swatch: '#166534', description: 'Calm and established', light: ['22 101 52', '255 255 255', '20 83 45'], dark: ['134 239 172', '15 23 42', '74 222 128'] },
  ocean: { label: 'Ocean', swatch: '#0369a1', description: 'Clear and dependable', light: ['3 105 161', '255 255 255', '14 116 144'], dark: ['125 211 252', '15 23 42', '103 232 249'] },
  terracotta: { label: 'Terracotta', swatch: '#c2410c', description: 'Earthy and assured', light: ['194 65 12', '255 255 255', '154 52 18'], dark: ['253 186 116', '15 23 42', '251 146 60'] },
  plum: { label: 'Plum', swatch: '#7e22ce', description: 'Modern and refined', light: ['126 34 206', '255 255 255', '157 23 77'], dark: ['216 180 254', '15 23 42', '249 168 212'] },
  blue: { label: 'Cobalt', swatch: '#2563eb', description: 'Bright and familiar', light: ['37 99 235', '255 255 255', '29 78 216'], dark: ['147 197 253', '15 23 42', '129 140 248'] },
  indigo: { label: 'Indigo', swatch: '#4f46e5', description: 'Focused and contemporary', light: ['79 70 229', '255 255 255', '109 40 217'], dark: ['165 180 252', '15 23 42', '196 181 253'] },
  violet: { label: 'Violet', swatch: '#7c3aed', description: 'Expressive and premium', light: ['124 58 237', '255 255 255', '147 51 234'], dark: ['196 181 253', '15 23 42', '216 180 254'] },
  teal: { label: 'Teal', swatch: '#0f766e', description: 'Balanced and composed', light: ['15 118 110', '255 255 255', '17 94 89'], dark: ['94 234 212', '15 23 42', '45 212 191'] },
  emerald: { label: 'Emerald', swatch: '#047857', description: 'Fresh and decisive', light: ['4 120 87', '255 255 255', '21 128 61'], dark: ['110 231 183', '15 23 42', '74 222 128'] },
  rose: { label: 'Rose', swatch: '#be123c', description: 'Bold and distinctive', light: ['190 18 60', '255 255 255', '159 18 57'], dark: ['253 164 175', '15 23 42', '251 113 133'] },
  slate: { label: 'Charcoal', swatch: '#334155', description: 'Neutral and understated', light: ['51 65 85', '255 255 255', '71 85 105'], dark: ['203 213 225', '15 23 42', '148 163 184'] },
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
    const def = ACCENTS[this.accent()] ?? ACCENTS.amber;
    const [brand, brandFg, companion] = dark ? def.dark : def.light;
    const root = document.documentElement.style;
    root.setProperty('--vs-brand', brand);
    root.setProperty('--vs-brand-fg', brandFg);
    root.setProperty('--vs-accent2', companion);
  }

  private initialMode(): ThemeMode {
    return (localStorage.getItem(STORAGE_KEY) as ThemeMode) || 'system';
  }

  private initialAccent(): Accent {
    const saved = localStorage.getItem(ACCENT_KEY) as Accent | null;
    return saved && saved in ACCENTS ? saved : 'amber';
  }
}

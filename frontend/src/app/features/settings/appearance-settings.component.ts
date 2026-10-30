import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ThemeService } from '@core/services/theme.service';
import { UiLanguageService } from '@core/i18n/ui-language.service';

/** Appearance settings: light/dark/system theme + brand accent colour.
 *  Mirrors the quick controls in the top bar, in one configurable place. */
@Component({
  selector: 'app-appearance-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <div class="mx-auto w-full">
      <h1 class="text-2xl font-bold text-content mb-1">Appearance</h1>
      <p class="text-content-muted mb-6">Choose your language, theme and accent colour. Saved on this device.</p>

      <section class="rounded-card bg-surface-raised border border-line shadow-card p-5 mb-5">
        <h2 class="font-semibold text-content mb-1">Interface language · इंटरफ़ेस की भाषा</h2>
        <p class="text-sm text-content-muted mb-4">Sign-up, the diary and the bare-act reader follow this; the rest of the app is in English for now, and the law texts stay as published.</p>
        <div class="grid grid-cols-2 gap-3">
          <button type="button" class="vs-mode" [class.vs-mode--active]="i18n.lang() === 'en'" (click)="i18n.set('en')"><mat-icon class="material-icons-outlined">translate</mat-icon><span>English</span></button>
          <button type="button" class="vs-mode" [class.vs-mode--active]="i18n.lang() === 'hi'" (click)="i18n.set('hi')" lang="hi"><mat-icon class="material-icons-outlined">translate</mat-icon><span>हिन्दी</span></button>
        </div>
      </section>

      <section class="rounded-card bg-surface-raised border border-line shadow-card p-5 mb-5">
        <h2 class="font-semibold text-content mb-1">Theme</h2>
        <p class="text-sm text-content-muted mb-4">Follow your system, or force light / dark.</p>
        <div class="grid grid-cols-3 gap-3">
          @for (m of modes; track m.key) {
            <button
              type="button"
              class="vs-mode"
              [class.vs-mode--active]="theme.mode() === m.key"
              (click)="theme.set(m.key)"
            >
              <mat-icon class="material-icons-outlined">{{ m.icon }}</mat-icon>
              <span>{{ m.label }}</span>
            </button>
          }
        </div>
      </section>

      <section class="rounded-card bg-surface-raised border border-line shadow-card p-5">
        <h2 class="font-semibold text-content mb-1">Accent colour</h2>
        <p class="text-sm text-content-muted mb-4">Recolours buttons, links, highlights and icons across the app.</p>
        <div class="accent-grid">
          @for (a of theme.accentList; track a.key) {
            <button
              type="button"
              class="vs-accent"
              [class.vs-accent--active]="theme.accent() === a.key"
              [attr.aria-label]="a.label"
              [title]="a.label"
              (click)="theme.setAccent(a.key)"
            >
              <span class="vs-accent__swatch" [style.background]="a.swatch">
                @if (theme.accent() === a.key) {
                  <mat-icon class="material-icons-outlined">check</mat-icon>
                }
              </span>
              <span><strong>{{ a.label }}</strong><small>{{ a.description }}</small></span>
            </button>
          }
        </div>
      </section>
    </div>
  `,
  styles: [
    `
      .vs-mode {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.4rem;
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid rgb(var(--vs-border));
        background: rgb(var(--vs-surface-sunken));
        color: rgb(var(--vs-text));
        cursor: pointer;
        font-size: 0.85rem;
        font-weight: 500;
        transition: border-color 0.15s ease, background 0.15s ease;
      }
      .vs-mode:hover {
        border-color: color-mix(in srgb, rgb(var(--vs-brand)) 40%, rgb(var(--vs-border)));
      }
      .vs-mode--active {
        border-color: rgb(var(--vs-brand));
        background: color-mix(in srgb, rgb(var(--vs-brand)) 10%, transparent);
        color: rgb(var(--vs-brand));
      }
      .accent-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 0.7rem;
      }
      .vs-accent {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        min-height: 64px;
        padding: 0.65rem;
        border-radius: 12px;
        border: 1px solid rgb(var(--vs-border));
        background: rgb(var(--vs-surface-sunken));
        cursor: pointer;
        color: rgb(var(--vs-text));
        text-align: left;
        transition: transform 0.1s ease, border-color 0.15s ease, background 0.15s ease;
      }
      .vs-accent:hover {
        transform: translateY(-1px);
      }
      .vs-accent--active {
        border-color: rgb(var(--vs-brand));
        background: color-mix(in srgb, rgb(var(--vs-brand)) 8%, rgb(var(--vs-surface-raised)));
      }
      .vs-accent__swatch {
        width: 38px;
        height: 38px;
        border-radius: 10px;
        display: grid;
        place-items: center;
        color: #fff;
        box-shadow: 0 2px 5px rgb(15 23 42 / 0.2);
        flex: 0 0 auto;
      }
      .vs-accent strong, .vs-accent small { display: block; }
      .vs-accent strong { font-size: 0.82rem; }
      .vs-accent small { margin-top: 0.14rem; color: rgb(var(--vs-text-muted)); font-size: 0.68rem; }
      .vs-accent mat-icon {
        font-size: 20px;
        width: 20px;
        height: 20px;
      }
    `,
  ],
})
export class AppearanceSettingsComponent {
  protected readonly theme = inject(ThemeService);
  protected readonly i18n = inject(UiLanguageService);
  protected readonly modes = [
    { key: 'light', label: 'Light', icon: 'light_mode' },
    { key: 'dark', label: 'Dark', icon: 'dark_mode' },
    { key: 'system', label: 'System', icon: 'contrast' },
  ] as const;
}

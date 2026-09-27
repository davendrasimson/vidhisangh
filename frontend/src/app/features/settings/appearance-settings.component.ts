import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ThemeService } from '@core/services/theme.service';

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
      <p class="text-content-muted mb-6">Choose your theme and accent colour. Saved on this device.</p>

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
        <div class="flex flex-wrap gap-3">
          @for (a of theme.accentList; track a.key) {
            <button
              type="button"
              class="vs-accent"
              [class.vs-accent--active]="theme.accent() === a.key"
              [style.background]="a.swatch"
              [attr.aria-label]="a.label"
              [title]="a.label"
              (click)="theme.setAccent(a.key)"
            >
              @if (theme.accent() === a.key) {
                <mat-icon class="material-icons-outlined">check</mat-icon>
              }
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
      .vs-accent {
        position: relative;
        width: 42px;
        height: 42px;
        border-radius: 11px;
        border: 2px solid transparent;
        cursor: pointer;
        display: grid;
        place-items: center;
        color: #fff;
        box-shadow: 0 1px 2px rgb(15 23 42 / 0.25);
        transition: transform 0.1s ease;
      }
      .vs-accent:hover {
        transform: translateY(-1px);
      }
      .vs-accent--active {
        border-color: rgb(var(--vs-text));
      }
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
  protected readonly modes = [
    { key: 'light', label: 'Light', icon: 'light_mode' },
    { key: 'dark', label: 'Dark', icon: 'dark_mode' },
    { key: 'system', label: 'System', icon: 'contrast' },
  ] as const;
}

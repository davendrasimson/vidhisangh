import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { UiLanguageService } from './ui-language.service';

/** One small button: "हिन्दी" while the interface is in English, "English" while in Hindi. */
@Component({
  selector: 'vs-language-toggle',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" class="vs-lang-toggle" (click)="i18n.toggle()"
      [attr.lang]="i18n.isHindi() ? 'en' : 'hi'"
      [attr.aria-label]="i18n.isHindi() ? 'Switch the interface to English' : 'इंटरफ़ेस हिन्दी में देखें'">
      {{ i18n.isHindi() ? 'English' : 'हिन्दी' }}
    </button>
  `,
  styles: [`
    .vs-lang-toggle { border: 1px solid rgb(var(--vs-border)); border-radius: 999px; padding: 0.2rem 0.75rem; font-size: 0.8rem; font-weight: 600; background: transparent; color: inherit; cursor: pointer; }
    .vs-lang-toggle:hover { background: rgb(var(--vs-brand) / 0.08); }
  `],
})
export class LanguageToggleComponent {
  protected readonly i18n = inject(UiLanguageService);
}

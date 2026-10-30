import { Pipe, PipeTransform, inject } from '@angular/core';
import { UiLanguageService } from './ui-language.service';

/** `{{ 'Sign in' | t }}` — the string in the chosen interface language.
 *  Impure so a language switch re-renders without the input changing. */
@Pipe({ name: 't', standalone: true, pure: false })
export class TPipe implements PipeTransform {
  private readonly i18n = inject(UiLanguageService);
  transform(text: string): string { return this.i18n.t(text); }
}

import { Pipe, PipeTransform, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

/**
 * Renders a search snippet (PostgreSQL `ts_headline` output) as HTML while
 * allowing **only** our own `<mark>` / `</mark>` highlight tags.
 *
 * Everything else — including any markup that may sit inside the judgment text
 * itself — is HTML-escaped first, so binding the result to `[innerHTML]` cannot
 * execute script or inject elements (security audit A-5). The backend escapes
 * the source before highlighting too; this pipe is the client-side guarantee.
 *
 * Usage: `<p [innerHTML]="j.snippet | snippet"></p>`
 */
@Pipe({ name: 'snippet', standalone: true, pure: true })
export class SnippetPipe implements PipeTransform {
  private readonly sanitizer = inject(DomSanitizer);

  transform(value: string | null | undefined): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(SnippetPipe.render(value));
  }

  /** Pure string form (unit-testable, no DOM): escape all, re-enable `<mark>`. */
  static render(value: string | null | undefined): string {
    if (!value) return '';
    const escaped = value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
    return escaped.replace(/&lt;(\/?)mark&gt;/g, '<$1mark>');
  }
}

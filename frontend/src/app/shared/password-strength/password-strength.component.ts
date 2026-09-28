import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { AbstractControl, ValidationErrors } from '@angular/forms';

// Mirrors the API's minimum structural policy. The API additionally checks its
// larger local common/breached-password deny-list before accepting a password.
export const STRONG_PASSWORD = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{8,}$/;

export function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const a = group.get('new_password')?.value;
  const b = group.get('confirm')?.value;
  return a && b && a !== b ? { mismatch: true } : null;
}

export type PasswordStrengthLevel = 'weak' | 'moderate' | 'strong';

export interface PasswordStrength {
  level: PasswordStrengthLevel;
  label: 'Weak' | 'Moderate' | 'Strong';
  score: 1 | 2 | 3;
  meetsMinimum: boolean;
  checks: {
    length: boolean;
    lower: boolean;
    upper: boolean;
    number: boolean;
    symbol: boolean;
  };
  guidance: string;
}

const COMMON_PATTERN = /(password|p@ssw|qwerty|123456|letmein|welcome|admin|india123)/i;

export function assessPassword(password: string): PasswordStrength {
  const checks = {
    length: password.length >= 8,
    lower: /[a-z]/.test(password),
    upper: /[A-Z]/.test(password),
    number: /\d/.test(password),
    symbol: /[^\w\s]/.test(password),
  };
  const variety = [checks.lower, checks.upper, checks.number, checks.symbol].filter(Boolean).length;
  const meetsMinimum = Object.values(checks).every(Boolean);
  const looksCommon = COMMON_PATTERN.test(password) || /(.)\1{3,}/.test(password);

  let level: PasswordStrengthLevel = 'weak';
  if (!looksCommon && meetsMinimum && password.length >= 12) level = 'strong';
  else if (!looksCommon && checks.length && variety >= 3) level = 'moderate';

  const missing: string[] = [];
  if (!checks.length) missing.push('8+ characters');
  if (!checks.lower) missing.push('a lowercase letter');
  if (!checks.upper) missing.push('an uppercase letter');
  if (!checks.number) missing.push('a number');
  if (!checks.symbol) missing.push('a symbol');

  const guidance = looksCommon
    ? 'Avoid common words, sequences and repeated characters.'
    : missing.length
      ? `Add ${missing.join(', ')}.`
      : level === 'strong'
        ? 'Strong and meets all password requirements.'
        : 'Meets the minimum. Use 12 or more characters for a stronger password.';

  return {
    level,
    label: level === 'strong' ? 'Strong' : level === 'moderate' ? 'Moderate' : 'Weak',
    score: level === 'strong' ? 3 : level === 'moderate' ? 2 : 1,
    meetsMinimum,
    checks,
    guidance,
  };
}

@Component({
  selector: 'vs-password-strength',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (password) {
      <div class="strength" [attr.data-level]="strength.level" aria-live="polite">
        <div class="strength__heading">
          <span>Password strength</span>
          <strong>{{ strength.label }}</strong>
        </div>
        <div
          class="strength__meter"
          role="meter"
          aria-valuemin="1"
          aria-valuemax="3"
          [attr.aria-valuenow]="strength.score"
          [attr.aria-valuetext]="strength.label"
          aria-label="Password strength"
        >
          <i [class.active]="strength.score >= 1"></i>
          <i [class.active]="strength.score >= 2"></i>
          <i [class.active]="strength.score >= 3"></i>
        </div>
        <p>{{ strength.guidance }}</p>
        <ul aria-label="Password requirements">
          <li [class.met]="strength.checks.length">8+ characters</li>
          <li [class.met]="strength.checks.upper && strength.checks.lower">Upper &amp; lower case</li>
          <li [class.met]="strength.checks.number">Number</li>
          <li [class.met]="strength.checks.symbol">Symbol</li>
        </ul>
      </div>
    }
  `,
  styles: [`
    :host { display: block; margin: -0.15rem 0 0.8rem; }
    .strength__heading { display: flex; justify-content: space-between; gap: .75rem; color: rgb(var(--vs-text-muted)); font-size: .72rem; }
    .strength__heading strong { color: var(--strength-color); font-weight: 750; }
    .strength__meter { display: grid; grid-template-columns: repeat(3,1fr); gap: .3rem; margin-top: .35rem; }
    .strength__meter i { height: .28rem; border-radius: 999px; background: rgb(var(--vs-border)); transition: background-color .18s ease; }
    .strength__meter i.active { background: var(--strength-color); }
    .strength p { margin: .4rem 0 0; color: rgb(var(--vs-text-muted)); font-size: .7rem; line-height: 1.4; }
    .strength ul { display: flex; flex-wrap: wrap; gap: .25rem .7rem; margin: .4rem 0 0; padding: 0; list-style: none; color: rgb(var(--vs-text-muted)); font-size: .67rem; }
    .strength li::before { content: '○'; margin-right: .24rem; }
    .strength li.met { color: rgb(var(--vs-success)); }
    .strength li.met::before { content: '✓'; }
    .strength[data-level='weak'] { --strength-color: rgb(var(--vs-danger)); }
    .strength[data-level='moderate'] { --strength-color: rgb(var(--vs-warning)); }
    .strength[data-level='strong'] { --strength-color: rgb(var(--vs-success)); }
  `],
})
export class PasswordStrengthComponent {
  @Input({ required: true }) password = '';

  get strength(): PasswordStrength {
    return assessPassword(this.password);
  }
}

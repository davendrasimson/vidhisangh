import { ChangeDetectionStrategy, Component, computed, forwardRef, input, signal } from '@angular/core';
import {
  AbstractControl, ControlValueAccessor, FormsModule, NG_VALIDATORS, NG_VALUE_ACCESSOR, ValidationErrors, Validator,
} from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

export interface DialCountry { iso: string; dial: string; name: string; digits: [number, number] }

/** India first (the default), then the countries members most often call from. */
export const DIAL_COUNTRIES: DialCountry[] = [
  { iso: 'IN', dial: '91', name: 'India', digits: [10, 10] },
  { iso: 'AE', dial: '971', name: 'United Arab Emirates', digits: [9, 9] },
  { iso: 'SA', dial: '966', name: 'Saudi Arabia', digits: [9, 9] },
  { iso: 'QA', dial: '974', name: 'Qatar', digits: [8, 8] },
  { iso: 'KW', dial: '965', name: 'Kuwait', digits: [8, 8] },
  { iso: 'OM', dial: '968', name: 'Oman', digits: [8, 8] },
  { iso: 'BH', dial: '973', name: 'Bahrain', digits: [8, 8] },
  { iso: 'NP', dial: '977', name: 'Nepal', digits: [10, 10] },
  { iso: 'BD', dial: '880', name: 'Bangladesh', digits: [10, 10] },
  { iso: 'LK', dial: '94', name: 'Sri Lanka', digits: [9, 9] },
  { iso: 'SG', dial: '65', name: 'Singapore', digits: [8, 8] },
  { iso: 'MY', dial: '60', name: 'Malaysia', digits: [9, 10] },
  { iso: 'HK', dial: '852', name: 'Hong Kong', digits: [8, 8] },
  { iso: 'GB', dial: '44', name: 'United Kingdom', digits: [10, 10] },
  { iso: 'US', dial: '1', name: 'United States / Canada', digits: [10, 10] },
  { iso: 'AU', dial: '61', name: 'Australia', digits: [9, 9] },
  { iso: 'NZ', dial: '64', name: 'New Zealand', digits: [8, 10] },
  { iso: 'DE', dial: '49', name: 'Germany', digits: [10, 11] },
  { iso: 'FR', dial: '33', name: 'France', digits: [9, 9] },
];

/** Split a stored "+919876543210" into country and national number (longest dial code wins). */
export function splitPhone(value: string | null | undefined): { country: DialCountry; national: string } {
  const digits = (value ?? '').replace(/\D/g, '');
  if ((value ?? '').trim().startsWith('+')) {
    const match = [...DIAL_COUNTRIES].sort((a, b) => b.dial.length - a.dial.length).find((c) => digits.startsWith(c.dial));
    if (match) return { country: match, national: digits.slice(match.dial.length) };
  }
  return { country: DIAL_COUNTRIES[0], national: digits };
}

/** "" when empty, else "+<dial><number>", which the API normalises and checks again. */
export function joinPhone(country: DialCountry, national: string): string {
  let digits = national.replace(/\D/g, '');
  // People paste "09876543210" or "+91 98765 43210" into the number box.
  if (digits.startsWith(country.dial) && digits.length > country.digits[1]) digits = digits.slice(country.dial.length);
  if (digits.startsWith('0') && digits.length > country.digits[1]) digits = digits.slice(1);
  return digits ? `+${country.dial}${digits}` : '';
}

export function phoneError(country: DialCountry, national: string): string | null {
  const digits = joinPhone(country, national).slice(1 + country.dial.length);
  if (!digits) return null;
  const [min, max] = country.digits;
  if (country.iso === 'IN' && !/^[6-9]\d{9}$/.test(digits)) return 'Enter the 10-digit mobile number, without 0 or +91.';
  if (digits.length < min || digits.length > max) {
    return min === max ? `Enter the ${min}-digit mobile number.` : `Enter a ${min}–${max} digit mobile number.`;
  }
  return null;
}

/**
 * Mobile number for WhatsApp codes: a country picker (India, +91, by default)
 * and a box for the national number only, so nobody has to guess the format.
 * The model value is the full international number, e.g. "+919876543210".
 *
 *   <vs-phone-input formControlName="phone" />
 *   <vs-phone-input name="phone" [(ngModel)]="phone" required />
 */
@Component({
  selector: 'vs-phone-input',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatFormFieldModule, MatInputModule, MatSelectModule],
  providers: [
    { provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => VsPhoneInputComponent), multi: true },
    { provide: NG_VALIDATORS, useExisting: forwardRef(() => VsPhoneInputComponent), multi: true },
  ],
  styles: [`
    :host { display: flex; gap: .5rem; align-items: flex-start; margin-bottom: 1.25rem; }
    .country { flex: 0 0 7.5rem; }
    .number { flex: 1 1 auto; min-width: 0; }
  `],
  template: `
    <mat-form-field appearance="outline" class="country" floatLabel="always" subscriptSizing="dynamic">
      <mat-label>Country</mat-label>
      <mat-select [value]="country()" (valueChange)="onCountry($event)" [disabled]="disabled()" aria-label="Country code"
                  panelWidth="18rem">
        <mat-select-trigger>{{ country().iso }} +{{ country().dial }}</mat-select-trigger>
        @for (c of countries; track c.iso) {
          <mat-option [value]="c">{{ c.name }} (+{{ c.dial }})</mat-option>
        }
      </mat-select>
    </mat-form-field>
    <mat-form-field appearance="outline" class="number" floatLabel="always" subscriptSizing="dynamic">
      <mat-label>{{ label() }}</mat-label>
      <input matInput type="tel" inputmode="numeric" autocomplete="tel-national" [placeholder]="placeholder()"
             [maxlength]="country().digits[1] + 4" [ngModel]="national()" (ngModelChange)="onNational($event)"
             [ngModelOptions]="{ standalone: true }" [disabled]="disabled()" (blur)="onTouched()" />
      @if (error()) { <mat-hint class="!text-danger">{{ error() }}</mat-hint> }
      @else if (hint()) { <mat-hint>{{ hint() }}</mat-hint> }
    </mat-form-field>
  `,
})
export class VsPhoneInputComponent implements ControlValueAccessor, Validator {
  readonly label = input('Mobile number');
  readonly hint = input<string>('');
  protected readonly countries = DIAL_COUNTRIES;
  protected readonly country = signal(DIAL_COUNTRIES[0]);
  protected readonly national = signal('');
  protected readonly disabled = signal(false);
  private readonly touched = signal(false);
  protected readonly placeholder = computed(() => {
    const [min, max] = this.country().digits;
    return min === max ? `${min}-digit mobile number` : 'Mobile number';
  });
  protected readonly error = computed(() => (this.touched() ? phoneError(this.country(), this.national()) : null));

  private onChange: (value: string) => void = () => {};
  protected onTouched: () => void = () => this.touched.set(true);

  writeValue(value: string | null): void {
    const { country, national } = splitPhone(value);
    this.country.set(country);
    this.national.set(national);
  }
  registerOnChange(fn: (value: string) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = () => { this.touched.set(true); fn(); }; }
  setDisabledState(disabled: boolean): void { this.disabled.set(disabled); }

  validate(_: AbstractControl): ValidationErrors | null {
    const message = phoneError(this.country(), this.national());
    return message ? { phone: message } : null;
  }

  protected onCountry(country: DialCountry): void {
    this.country.set(country);
    this.onChange(joinPhone(country, this.national()));
  }

  protected onNational(value: string): void {
    this.national.set(value);
    this.onChange(joinPhone(this.country(), value));
  }
}

import { ChangeDetectionStrategy, Component, forwardRef, input, signal } from '@angular/core';
import { ControlValueAccessor, FormsModule, NG_VALUE_ACCESSOR } from '@angular/forms';
import { DateAdapter, MAT_DATE_FORMATS, MAT_DATE_LOCALE } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatIconModule } from '@angular/material/icon';
import {
  IndianDateAdapter,
  VS_DATE_FORMATS,
  fromIsoDate,
  toIsoDate,
} from '@core/dates/indian-date-adapter';
import { utcOffset } from './utc-offset';

/**
 * The product's date field: typed or picked as dd/mm/yyyy, whatever the
 * browser's locale (a native `<input type="date">` renders mm/dd/yyyy for
 * many users and cannot be told otherwise).
 *
 * Model value is what the API stores: "yyyy-mm-dd", or with `withTime`
 * "yyyy-mm-ddTHH:mm+05:30" — the time as typed, with this device's UTC offset.
 * Without the offset the server read 10:30 as UTC, so a 10:30 hearing showed
 * (and was reminded) as 4:00 pm in India. Values from the API ("…Z") are shown
 * in local time.
 *
 *   <vs-date-input [(ngModel)]="form.next_hearing_date" />
 *   <vs-date-input withTime [(ngModel)]="form.start_at" />
 */
@Component({
  selector: 'vs-date-input',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatDatepickerModule, MatIconModule],
  providers: [
    { provide: DateAdapter, useClass: IndianDateAdapter },
    { provide: MAT_DATE_FORMATS, useValue: VS_DATE_FORMATS },
    { provide: MAT_DATE_LOCALE, useValue: 'en-IN' },
    { provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => VsDateInputComponent), multi: true },
  ],
  template: `
    <div class="vs-input flex items-center gap-1 !p-0 !pr-1" [class.opacity-60]="disabled()">
      <input
        class="min-w-0 flex-1 bg-transparent border-0 outline-none px-3 py-2 text-inherit placeholder:text-content-muted"
        [matDatepicker]="picker"
        [min]="minDate()"
        [max]="maxDate()"
        [ngModel]="date()"
        (ngModelChange)="onDate($event)"
        [disabled]="disabled()"
        (blur)="onTouched()"
        placeholder="dd/mm/yyyy"
        inputmode="numeric"
        [attr.aria-label]="label()"
      />
      @if (withTime()) {
        <input
          type="time"
          class="bg-transparent border-0 outline-none px-1 py-2 text-inherit w-[6.5rem]"
          [ngModel]="time()"
          (ngModelChange)="onTime($event)"
          [disabled]="disabled()"
          (blur)="onTouched()"
          aria-label="Time"
        />
      }
      <mat-datepicker-toggle [for]="picker" [disabled]="disabled()">
        <mat-icon matDatepickerToggleIcon class="material-icons-outlined">calendar_today</mat-icon>
      </mat-datepicker-toggle>
      <mat-datepicker #picker />
    </div>
  `,
  styles: [`:host { display: block; }`],
})
export class VsDateInputComponent implements ControlValueAccessor {
  /** Also collect a time; model becomes "yyyy-mm-ddTHH:mm". */
  readonly withTime = input(false, { transform: (v: unknown) => v !== false && v !== 'false' });
  readonly label = input('Date');
  /** Bounds as ISO date strings, like the native input's min/max. */
  readonly min = input<string | null>(null);
  readonly max = input<string | null>(null);

  protected readonly date = signal<Date | null>(null);
  protected readonly time = signal<string>('');
  protected readonly disabled = signal(false);
  protected readonly minDate = () => fromIsoDate(this.min());
  protected readonly maxDate = () => fromIsoDate(this.max());

  private onChange: (v: string | null) => void = () => {};
  protected onTouched: () => void = () => {};

  writeValue(value: string | null): void {
    // A stored date-time ("…Z" or "…+05:30") is shown in this device's time.
    if (value && /T\d{2}:\d{2}.*(Z|[+-]\d{2}:?\d{2})$/.test(value)) {
      const d = new Date(value);
      if (!isNaN(d.getTime())) {
        this.date.set(new Date(d.getFullYear(), d.getMonth(), d.getDate()));
        this.time.set(`${pad(d.getHours())}:${pad(d.getMinutes())}`);
        return;
      }
    }
    this.date.set(fromIsoDate(value));
    const t = value?.match(/T(\d{2}:\d{2})/);
    this.time.set(t ? t[1] : '');
  }
  registerOnChange(fn: (v: string | null) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }
  setDisabledState(isDisabled: boolean): void { this.disabled.set(isDisabled); }

  protected onDate(d: Date | null): void {
    this.date.set(d);
    this.emit();
  }
  protected onTime(t: string): void {
    this.time.set(t);
    this.emit();
  }

  private emit(): void {
    const iso = toIsoDate(this.date());
    if (!iso) {
      this.onChange(null);
      return;
    }
    if (!this.withTime()) {
      this.onChange(iso);
      return;
    }
    // A date without a time is still a value: default to the start of the day.
    const time = this.time() || '00:00';
    this.onChange(`${iso}T${time}${utcOffset(new Date(`${iso}T${time}`))}`);
  }
}

function pad(n: number): string {
  return String(n).padStart(2, '0');
}


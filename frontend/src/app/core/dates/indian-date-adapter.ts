import { Injectable } from '@angular/core';
import { MatDateFormats, NativeDateAdapter } from '@angular/material/core';

/** The one date format the product shows and accepts: dd/mm/yyyy. */
export const VS_DATE_FORMAT = 'dd/MM/yyyy';
export const VS_DATETIME_FORMAT = 'dd/MM/yyyy, h:mm a';

/**
 * Material's NativeDateAdapter parses with `Date.parse`, which reads
 * "25/09/2026" as invalid (or, worse, "09/12/2026" as 12 September). This
 * adapter reads and writes day-first, and starts the week on Monday.
 */
@Injectable()
export class IndianDateAdapter extends NativeDateAdapter {
  override parse(value: unknown): Date | null {
    if (value instanceof Date) return value;
    if (typeof value === 'number') return new Date(value);
    if (typeof value !== 'string' || !value.trim()) return null;
    const m = value.trim().match(/^(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2,4})$/);
    if (!m) {
      // ISO "yyyy-mm-dd" (from the API) is still accepted.
      const iso = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
      return iso ? new Date(+iso[1], +iso[2] - 1, +iso[3]) : null;
    }
    const day = +m[1];
    const month = +m[2] - 1;
    const year = m[3].length === 2 ? 2000 + +m[3] : +m[3];
    const d = new Date(year, month, day);
    // Reject 31/02/2026 rather than silently rolling into March.
    return d.getDate() === day && d.getMonth() === month ? d : null;
  }

  override format(date: Date, displayFormat: object | string): string {
    if (displayFormat === 'input') {
      const dd = String(date.getDate()).padStart(2, '0');
      const mm = String(date.getMonth() + 1).padStart(2, '0');
      return `${dd}/${mm}/${date.getFullYear()}`;
    }
    return super.format(date, displayFormat);
  }

  override getFirstDayOfWeek(): number {
    return 1; // Monday
  }
}

export const VS_DATE_FORMATS: MatDateFormats = {
  parse: { dateInput: 'input' },
  display: {
    dateInput: 'input',
    monthYearLabel: { year: 'numeric', month: 'short' },
    dateA11yLabel: { year: 'numeric', month: 'long', day: 'numeric' },
    monthYearA11yLabel: { year: 'numeric', month: 'long' },
  },
};

/** Date -> "yyyy-mm-dd" in local time (what the API stores for a date field). */
export function toIsoDate(d: Date | null): string | null {
  if (!d || isNaN(d.getTime())) return null;
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** "yyyy-mm-dd" or an ISO date-time -> local Date (date part only). */
export function fromIsoDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}

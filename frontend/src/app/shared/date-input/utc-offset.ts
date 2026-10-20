/** "+05:30" in India: this device's UTC offset on that date (DST-aware elsewhere). */
export function utcOffset(local: Date): string {
  const minutes = -local.getTimezoneOffset();
  const sign = minutes >= 0 ? '+' : '-';
  const abs = Math.abs(minutes);
  return `${sign}${String(Math.floor(abs / 60)).padStart(2, '0')}:${String(abs % 60).padStart(2, '0')}`;
}

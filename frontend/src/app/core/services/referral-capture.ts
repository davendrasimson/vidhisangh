/**
 * Invite codes from a colleague's link (`?ref=ABC2345`). Kept in the browser
 * until sign-up, because people land on the home page or a bare-act page and
 * only register later. Storage can be missing or blocked; then the code is
 * simply not credited.
 */
const KEY = 'vs_ref';

export function captureReferral(search: string): void {
  const code = new URLSearchParams(search).get('ref')?.trim().toUpperCase();
  if (!code || !/^[2-9A-Z]{4,16}$/.test(code)) return;
  try { localStorage.setItem(KEY, code); } catch { /* storage unavailable */ }
}

export function pendingReferral(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

export function clearReferral(): void {
  try { localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}

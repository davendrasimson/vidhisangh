/**
 * Where to go after signing up from a public page ("Save this section",
 * "Judgments on this section"). Kept on the device because the account may be
 * finished later (email verification) or on another screen; used once.
 */
const KEY = 'vs_after_signup';

/** In-app paths only: "/app/…", no scheme, no "//", no backslash. */
export function safeNext(url: string | null | undefined): string | null {
  return url && url.startsWith('/app/') && !url.startsWith('//') && !url.includes('\\') && !url.includes(':') ? url : null;
}

export function rememberNext(url: string | null | undefined): void {
  const next = safeNext(url);
  if (!next) return;
  try { localStorage.setItem(KEY, JSON.stringify({ next, at: Date.now() })); } catch { /* storage unavailable */ }
}

/** The remembered destination (valid for a week), removed once read. */
export function takeNext(): string | null {
  try {
    const raw = localStorage.getItem(KEY);
    localStorage.removeItem(KEY);
    if (!raw) return null;
    const { next, at } = JSON.parse(raw) as { next: string; at: number };
    return Date.now() - at < 7 * 86_400_000 ? safeNext(next) : null;
  } catch { return null; }
}

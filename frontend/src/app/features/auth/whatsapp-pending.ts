/**
 * A WhatsApp code in progress, kept on the device so leaving the app to read
 * the code never loses it. On a phone, switching to WhatsApp can restart the
 * app's screens (Android reclaims it, or an update is applied); without this
 * the person lands on an empty form, asks for another code and hits the
 * server's one-a-minute, five-an-hour limit.
 *
 * Holds the number, the challenge id (useless without the code) and, after a
 * verified code for a new number, the short-lived sign-up pass. Everything
 * expires with the server's own deadline and is cleared once used.
 */
export interface WhatsAppPending {
  phone: string;
  challenge: string | null;
  /** Epoch ms: the code (or sign-up pass) stops working. */
  expiresAt: number;
  /** Epoch ms: a new code can be asked for. */
  resendAt: number;
  signup?: { signup_id: string; signup_token: string; expiresAt: number } | null;
}

export const PENDING_KEY = 'vs_wa_pending';

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function store(): Store | null {
  try { return typeof localStorage === 'undefined' ? null : localStorage; } catch { return null; }
}

/** The saved state, or null if there is none or it has expired. */
export function loadPending(now = Date.now(), s: Store | null = store()): WhatsAppPending | null {
  try {
    const raw = s?.getItem(PENDING_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as WhatsAppPending;
    const live = p.signup ? p.signup.expiresAt > now : p.expiresAt > now || p.resendAt > now;
    if (typeof p.phone !== 'string' || !live) { s?.removeItem(PENDING_KEY); return null; }
    return p;
  } catch { return null; }
}

export function savePending(p: WhatsAppPending, s: Store | null = store()): void {
  try { s?.setItem(PENDING_KEY, JSON.stringify(p)); } catch { /* storage unavailable */ }
}

export function clearPending(s: Store | null = store()): void {
  try { s?.removeItem(PENDING_KEY); } catch { /* storage unavailable */ }
}

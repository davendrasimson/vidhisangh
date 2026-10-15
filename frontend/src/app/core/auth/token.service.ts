import { Injectable, signal } from '@angular/core';
import { environment } from '@env/environment';
import { TokenPair } from '@core/models/auth.models';

interface AccessClaims {
  sub: string;
  tid: string | null;
  scopes: string[];
  superuser?: boolean;
  exp: number;
  /** Session epoch — see backend app/core/revocation.py. */
  ep?: number;
  /** "password must change": the session may only call /auth/change-password. */
  pmc?: boolean;
}

/** Non-secret marker: "this browser has a session cookie worth trying". */
const SESSION_KEY = 'vs.session';
/** Last known profile + permissions, so the app opens signed in while offline. */
const PROFILE_KEY = 'vs.profile-cache';
/** Stable, non-secret ID used only to replace stale sessions from this browser. */
const DEVICE_KEY = 'vs.device-id';

/** Prefixes of everything this app keeps in localStorage. */
export const APP_STORAGE_PREFIXES = ['vs.', 'vidhisangh-'];

/**
 * Token custody (audit A-11).
 * - The **access token** lives only in memory (a signal), limiting XSS blast
 *   radius and never persisting a bearer credential to disk.
 * - The **refresh token** is an HttpOnly, SameSite=Strict cookie scoped to the
 *   API's `/auth` path — set and rotated by the server, invisible to scripts.
 *   The only thing stored here is a marker saying a session may exist, so a
 *   fresh tab knows whether to attempt a silent refresh.
 */
@Injectable({ providedIn: 'root' })
export class TokenService {
  readonly accessToken = signal<string | null>(null);

  /** True when a refresh cookie was issued to this browser (best knowledge). */
  get hasSession(): boolean {
    try {
      return localStorage.getItem(SESSION_KEY) === '1';
    } catch {
      return false;
    }
  }

  get deviceId(): string {
    try {
      const existing = localStorage.getItem(DEVICE_KEY);
      if (existing) return existing;
      const created = typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${crypto.getRandomValues(new Uint32Array(4)).join('-')}`;
      localStorage.setItem(DEVICE_KEY, created);
      return created;
    } catch {
      return typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-browser-session`;
    }
  }

  get deviceLabel(): string {
    const ua = navigator.userAgent;
    const os = /Windows/.test(ua) ? 'Windows' : /Macintosh|Mac OS X/.test(ua) ? 'macOS'
      : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS'
      : /Linux/.test(ua) ? 'Linux' : 'this device';
    const browser = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox'
      : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
    return `${browser} on ${os}`;
  }

  setSession(pair: TokenPair): void {
    this.accessToken.set(pair.access_token);
    try {
      localStorage.setItem(SESSION_KEY, '1');
    } catch {
      /* storage unavailable (private mode) — the cookie alone still works */
    }
  }

  /** Drop the in-memory token and every app key in localStorage. */
  clear(): void {
    this.accessToken.set(null);
    try {
      const doomed: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key !== DEVICE_KEY && APP_STORAGE_PREFIXES.some((p) => key.startsWith(p))) doomed.push(key);
      }
      doomed.forEach((k) => localStorage.removeItem(k));
    } catch {
      /* storage unavailable */
    }
  }

  /** Remember who is signed in (no credentials): used only while the server cannot be reached. */
  cacheProfile(user: unknown, scopes: string[]): void {
    try { localStorage.setItem(PROFILE_KEY, JSON.stringify({ user, scopes })); } catch { /* storage unavailable */ }
  }

  cachedProfile<T>(): { user: T; scopes: string[] } | null {
    try {
      const raw = localStorage.getItem(PROFILE_KEY);
      return raw ? JSON.parse(raw) as { user: T; scopes: string[] } : null;
    } catch {
      return null;
    }
  }

  /** Forget only the in-memory access token (another tab signed out). */
  dropAccessToken(): void {
    this.accessToken.set(null);
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
  }

  claims(): AccessClaims | null {
    const token = this.accessToken();
    if (!token) return null;
    try {
      const payload = token.split('.')[1];
      const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
      return JSON.parse(json) as AccessClaims;
    } catch {
      return null;
    }
  }

  /** True when the current session is restricted to changing its password. */
  mustChangePassword(): boolean {
    return this.claims()?.pmc === true;
  }

  /** True when the access token is missing or within the refresh skew window. */
  isAccessExpired(): boolean {
    const claims = this.claims();
    if (!claims) return true;
    const now = Math.floor(Date.now() / 1000);
    return claims.exp - environment.tokenRefreshSkewSeconds <= now;
  }
}

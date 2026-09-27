import { Injectable, signal } from '@angular/core';
import { environment } from '@env/environment';
import { TokenPair } from '@core/models/auth.models';

interface AccessClaims {
  sub: string;
  tid: string | null;
  scopes: string[];
  superuser?: boolean;
  exp: number;
}

const REFRESH_KEY = 'vs.refresh';

/**
 * Token custody.
 * - The **access token** lives only in memory (a signal), limiting XSS blast
 *   radius and never persisting a bearer credential to disk.
 * - The **refresh token** is persisted so a page reload can silently
 *   re-establish a session; it is opaque and single-use (rotated server-side).
 */
@Injectable({ providedIn: 'root' })
export class TokenService {
  readonly accessToken = signal<string | null>(null);

  get refreshToken(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  }

  setSession(pair: TokenPair): void {
    this.accessToken.set(pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  }

  clear(): void {
    this.accessToken.set(null);
    localStorage.removeItem(REFRESH_KEY);
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

  /** True when the access token is missing or within the refresh skew window. */
  isAccessExpired(): boolean {
    const claims = this.claims();
    if (!claims) return true;
    const now = Math.floor(Date.now() / 1000);
    return claims.exp - environment.tokenRefreshSkewSeconds <= now;
  }
}

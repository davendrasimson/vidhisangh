import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { tap } from 'rxjs/operators';
import { environment } from '@env/environment';
import {
  AuthSession,
  LoginRequest,
  OAuthAuthorize,
  RegisterRequest,
  SsoProvider,
  TokenPair,
  User,
} from '@core/models/auth.models';
import { TokenService } from './token.service';

type AuthStatus = 'idle' | 'authenticating' | 'authenticated' | 'anonymous';

/**
 * Authentication signal store.
 *
 * Holds reactive session state with Angular signals (the same reactive model
 * NgRx Signal Store builds upon) so components bind directly to `user`,
 * `isAuthenticated`, and `permissions` with zero boilerplate.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly tokens = inject(TokenService);
  private readonly api = environment.apiBaseUrl;

  private readonly _user = signal<User | null>(null);
  private readonly _status = signal<AuthStatus>('idle');

  readonly user = this._user.asReadonly();
  readonly status = this._status.asReadonly();
  readonly isAuthenticated = computed(() => this._status() === 'authenticated');
  readonly permissions = computed(() => this.tokens.claims()?.scopes ?? []);

  hasPermission(code: string): boolean {
    const scopes = this.permissions();
    return this._user()?.is_superuser === true || scopes.includes('*') || scopes.includes(code);
  }

  register(payload: RegisterRequest): Observable<TokenPair> {
    this._status.set('authenticating');
    return this.http.post<TokenPair>(`${this.api}/auth/register`, payload).pipe(
      tap((pair) => this.tokens.setSession(pair)),
    );
  }

  login(payload: LoginRequest): Observable<TokenPair> {
    this._status.set('authenticating');
    return this.http.post<TokenPair>(`${this.api}/auth/login`, payload).pipe(
      tap((pair) => this.tokens.setSession(pair)),
    );
  }

  // ── Sessions / devices ──────────────────────────────────────────
  sessions(): Observable<AuthSession[]> {
    return this.http.get<AuthSession[]>(`${this.api}/auth/sessions`);
  }

  revokeSession(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/auth/sessions/${id}`);
  }

  revokeOtherSessions(): Observable<{ revoked: number }> {
    return this.http.post<{ revoked: number }>(`${this.api}/auth/sessions/revoke-others`, {});
  }

  // ── SSO (OAuth/OIDC) ────────────────────────────────────────────
  ssoProviders(): Observable<SsoProvider[]> {
    return this.http.get<SsoProvider[]>(`${this.api}/auth/oauth/providers`);
  }

  ssoAuthorize(provider: string, redirectUri: string, loginHint?: string): Observable<OAuthAuthorize> {
    return this.http.post<OAuthAuthorize>(`${this.api}/auth/oauth/${provider}/authorize`, {
      redirect_uri: redirectUri,
      login_hint: loginHint ?? null,
    });
  }

  ssoCallback(provider: string, code: string, state: string): Observable<TokenPair> {
    this._status.set('authenticating');
    return this.http
      .post<TokenPair>(`${this.api}/auth/oauth/${provider}/callback`, { code, state })
      .pipe(tap((pair) => this.tokens.setSession(pair)));
  }

  /** Exchange the stored refresh token for a fresh access token (rotation). */
  refresh(): Observable<TokenPair> {
    const refresh_token = this.tokens.refreshToken ?? '';
    return this.http
      .post<TokenPair>(`${this.api}/auth/refresh`, { refresh_token })
      .pipe(tap((pair) => this.tokens.setSession(pair)));
  }

  loadCurrentUser(): Observable<User> {
    return this.http
      .get<User>(`${this.api}/auth/me`)
      .pipe(tap((user) => {
        this._user.set(user);
        this._status.set('authenticated');
      }));
  }

  async logout(allDevices = false): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(`${this.api}/auth/logout`, {
          refresh_token: this.tokens.refreshToken,
          all_devices: allDevices,
        }),
      );
    } catch {
      /* best-effort — clear locally regardless */
    }
    this.tokens.clear();
    this._user.set(null);
    this._status.set('anonymous');
  }

  /**
   * On app start / route activation, establish a session from a persisted
   * refresh token. Returns true if authenticated.
   */
  async restoreSession(): Promise<boolean> {
    if (this.isAuthenticated()) return true;
    if (!this.tokens.refreshToken) {
      this._status.set('anonymous');
      return false;
    }
    // The access token lives only in memory, so every tab that boots must
    // refresh — and refresh tokens rotate. Two tabs booting together would
    // present the same stored token twice, which the server treats as reuse.
    // A cross-tab lock makes them take turns: the second tab, once it gets
    // the lock, reads the token the first tab just stored.
    const locks = (navigator as Navigator & { locks?: LockManager }).locks;
    if (locks) {
      return locks.request('vs.session-restore', () => this.restoreSessionUnlocked());
    }
    return this.restoreSessionUnlocked();
  }

  private async restoreSessionUnlocked(): Promise<boolean> {
    if (this.isAuthenticated()) return true;
    for (let attempt = 0; ; attempt++) {
      try {
        if (this.tokens.isAccessExpired()) {
          await firstValueFrom(this.refresh());
        }
        await firstValueFrom(this.loadCurrentUser());
        return true;
      } catch (err) {
        const status = err instanceof HttpErrorResponse ? err.status : 0;
        // A 429 on a hard refresh is the rate limiter, not an expired
        // session: wait what it asks for (bounded) and try once more.
        if (status === 429 && attempt === 0) {
          const retryAfter = Number(err instanceof HttpErrorResponse ? err.error?.details?.retry_after : 0);
          await new Promise((r) => setTimeout(r, Math.min(Math.max(retryAfter, 1), 15) * 1000));
          continue;
        }
        // Only a rejected token means the session is gone. Anything else
        // (rate limit, network, server error) keeps the tokens so the next
        // navigation can try again instead of forcing a new sign-in.
        if (status === 401 || status === 403) this.tokens.clear();
        this._status.set('anonymous');
        return false;
      }
    }
  }
}

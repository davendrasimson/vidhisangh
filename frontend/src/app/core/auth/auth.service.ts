import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, firstValueFrom } from 'rxjs';
import { tap } from 'rxjs/operators';
import { environment } from '@env/environment';
import { clearReferral, pendingReferral } from '@core/services/referral-capture';
import { AuthSession, LoginRequest, OAuthAuthorize, RegisterRequest, RegistrationPending, PhoneOtpResponse, SsoProvider, TokenPair, User, WhatsAppSignupRequest, WhatsAppSignupRequired } from '@core/models/auth.models';
import { TokenService } from './token.service';

/** sessionStorage key: which SSO provider the callback page is finishing. */
export const SSO_PROVIDER_KEY = 'vs_sso_provider';

type AuthStatus = 'idle' | 'authenticating' | 'authenticated' | 'anonymous';

/** Custom header the API requires on cookie-based auth calls (CSRF defence). */
export const CSRF_HEADER = { 'X-Requested-With': 'VidhiSangh' };
/** Cross-tab channel: a sign-out in one tab signs every tab out. */
const AUTH_CHANNEL = 'vs-auth';

/**
 * Authentication signal store.
 *
 * Holds reactive session state with Angular signals (the same reactive model
 * NgRx Signal Store builds upon) so components bind directly to `user`,
 * `isAuthenticated`, and `permissions` with zero boilerplate.
 *
 * The refresh token is an HttpOnly cookie the browser sends on `/auth/refresh`
 * and `/auth/logout` (`withCredentials`), never readable here (audit A-11).
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly tokens = inject(TokenService);
  private readonly router = inject(Router);
  private readonly api = environment.apiBaseUrl;
  private readonly channel: BroadcastChannel | null =
    typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(AUTH_CHANNEL) : null;

  private readonly _user = signal<User | null>(null);
  private readonly _status = signal<AuthStatus>('idle');

  readonly user = this._user.asReadonly();
  readonly status = this._status.asReadonly();
  readonly isAuthenticated = computed(() => this._status() === 'authenticated');
  /**
   * Signed in, but the server cannot be reached (no network, weak signal, a
   * deploy restarting the API). The person stays signed in with their last
   * known profile; only a rejected refresh token (401/403) or "Sign out" ends
   * the session.
   */
  readonly offline = signal(false);
  private readonly cachedScopes = signal<string[]>([]);
  readonly permissions = computed(() => this.tokens.claims()?.scopes ?? (this.offline() ? this.cachedScopes() : []));
  /** Sitting judicial officer (token claim `jud`): the app shows the judge's view. */
  readonly isJudicial = computed(() => this.tokens.claims()?.jud === true);
  private reconnectTimer: ReturnType<typeof setInterval> | null = null;
  private bootedOffline = false;

  constructor() {
    if (this.channel) {
      this.channel.onmessage = (e: MessageEvent<{ type?: string }>) => {
        if (e.data?.type === 'logout') this.onRemoteLogout();
      };
    }
  }

  hasPermission(code: string): boolean {
    const scopes = this.permissions();
    return this._user()?.is_superuser === true || scopes.includes('*') || scopes.includes(code);
  }

  /** True when the session may only change its (temporary) password. */
  mustChangePassword(): boolean {
    return this.tokens.mustChangePassword();
  }

  register(payload: RegisterRequest): Observable<TokenPair | RegistrationPending> {
    this._status.set('authenticating');
    return this.http
      .post<TokenPair | RegistrationPending>(`${this.api}/auth/register`, {
        ...payload,
        device_id: this.tokens.deviceId,
        referral_code: pendingReferral(),
      }, { withCredentials: true })
      .pipe(tap((result) => {
        clearReferral();
        if ('access_token' in result) this.tokens.setSession(result);
        else this._status.set('anonymous');
      }));
  }

  authOptions(): Observable<{ whatsapp_available: boolean }> {
    return this.http.get<{ whatsapp_available: boolean }>(`${this.api}/auth/options`);
  }

  requestWhatsAppCode(phone: string, purpose: 'register' | 'login'): Observable<PhoneOtpResponse> {
    return this.http.post<PhoneOtpResponse>(`${this.api}/auth/whatsapp/request`, { phone, purpose });
  }

  /** Signs in, or, for a number with no account yet, returns a pass for `whatsappSignup`. */
  whatsappLogin(challenge_id: string, code: string, mfa_code?: string): Observable<TokenPair | WhatsAppSignupRequired> {
    return this.http.post<TokenPair | WhatsAppSignupRequired>(`${this.api}/auth/whatsapp/login`, {
      challenge_id, code, mfa_code: mfa_code || null, device_id: this.tokens.deviceId,
    }, { withCredentials: true }).pipe(tap(result => { if ('access_token' in result) this.tokens.setSession(result); }));
  }

  /** Finish a WhatsApp sign-up: creates an individual account and signs in. */
  whatsappSignup(payload: WhatsAppSignupRequest): Observable<TokenPair> {
    return this.http.post<TokenPair>(`${this.api}/auth/whatsapp/signup`, {
      ...payload, device_id: this.tokens.deviceId, referral_code: pendingReferral(),
    }, { withCredentials: true }).pipe(tap(pair => { clearReferral(); this.tokens.setSession(pair); }));
  }

  resendPublicVerification(email: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.api}/auth/resend-verification-public`, { email });
  }

  login(payload: LoginRequest): Observable<TokenPair> {
    this._status.set('authenticating');
    return this.http
      .post<TokenPair>(`${this.api}/auth/login`, {
        ...payload,
        device_id: this.tokens.deviceId,
        device_label: payload.device_label ?? this.tokens.deviceLabel,
      }, { withCredentials: true })
      .pipe(tap((pair) => this.tokens.setSession(pair)));
  }

  // ── Password reset / email verification ─────────────────────────
  forgotPassword(email: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.api}/auth/forgot-password`, { email });
  }

  resetPassword(token: string, newPassword: string): Observable<void> {
    return this.http.post<void>(`${this.api}/auth/reset-password`, {
      token,
      new_password: newPassword,
    });
  }

  verifyEmail(token: string): Observable<{ verified: boolean }> {
    return this.http.post<{ verified: boolean }>(`${this.api}/auth/verify-email/${encodeURIComponent(token)}`, {});
  }

  resendVerification(): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.api}/auth/resend-verification`, {});
  }

  changePassword(currentPassword: string, newPassword: string): Observable<void> {
    return this.http.post<void>(`${this.api}/auth/change-password`, {
      current_password: currentPassword,
      new_password: newPassword,
    });
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
      .post<TokenPair>(`${this.api}/auth/oauth/${provider}/callback`,
        { code, state, referral_code: pendingReferral() }, { withCredentials: true })
      .pipe(tap((pair) => {
        if (pair.new_account) clearReferral();
        this.tokens.setSession(pair);
      }));
  }

  /** Leave for the provider's sign-in page; `/auth/callback` finishes (and signs up new people). */
  async startSso(provider: string): Promise<void> {
    const redirectUri = `${window.location.origin}/auth/callback`;
    const { authorize_url } = await firstValueFrom(this.ssoAuthorize(provider, redirectUri));
    sessionStorage.setItem(SSO_PROVIDER_KEY, provider);
    window.location.href = authorize_url;
  }

  /** Exchange the HttpOnly refresh cookie for a fresh access token (rotation). */
  refresh(): Observable<TokenPair> {
    return this.http
      .post<TokenPair>(
        `${this.api}/auth/refresh`,
        { device_id: this.tokens.deviceId },
        { withCredentials: true, headers: CSRF_HEADER },
      )
      .pipe(tap((pair) => this.tokens.setSession(pair)));
  }

  loadCurrentUser(): Observable<User> {
    return this.http
      .get<User>(`${this.api}/auth/me`)
      .pipe(tap((user) => {
        this._user.set(user);
        this._status.set('authenticated');
        this.tokens.cacheProfile(user, this.tokens.claims()?.scopes ?? []);
      }));
  }

  /** Add a mobile number to my account: a WhatsApp code is sent to it. */
  requestMyPhoneCode(phone: string): Observable<PhoneOtpResponse> {
    return this.http.post<PhoneOtpResponse>(`${this.api}/auth/me/phone/request`, { phone });
  }

  verifyMyPhone(challenge_id: string, code: string): Observable<User> {
    return this.http
      .post<User>(`${this.api}/auth/me/phone/verify`, { challenge_id, code })
      .pipe(tap((user) => this._user.set(user)));
  }

  acceptCurrentTerms(): Observable<User> {
    return this.http
      .post<User>(`${this.api}/auth/me/accept-terms`, { accept_terms: true })
      .pipe(tap((user) => this._user.set(user)));
  }

  async logout(allDevices = false): Promise<void> {
    // While still signed in: this phone stops receiving the member's pushes.
    const { forgetPushDevice } = await import('@core/platform/push');
    await forgetPushDevice(this.http);
    try {
      await firstValueFrom(
        this.http.post(
          `${this.api}/auth/logout`,
          { all_devices: allDevices },
          { withCredentials: true, headers: CSRF_HEADER },
        ),
      );
    } catch {
      /* best-effort — clear locally regardless */
    }
    await this.clearLocalState();
    this.channel?.postMessage({ type: 'logout' });
  }

  /** Forget everything this browser holds for the session (audit A-11 / P-9). */
  private async clearLocalState(): Promise<void> {
    this.offline.set(false);
    this.stopReconnecting();
    this.tokens.clear();
    this._user.set(null);
    this._status.set('anonymous');
    try {
      if (typeof caches !== 'undefined') {
        const names = await caches.keys();
        await Promise.all(names.map((n) => caches.delete(n)));
      }
    } catch {
      /* CacheStorage unavailable */
    }
  }

  private onRemoteLogout(): void {
    this.tokens.dropAccessToken();
    this._user.set(null);
    this._status.set('anonymous');
    if (!this.router.url.startsWith('/auth')) {
      void this.router.navigateByUrl('/auth/login');
    }
  }

  /**
   * On app start / route activation, establish a session from the refresh
   * cookie. Returns true if authenticated.
   */
  async restoreSession(): Promise<boolean> {
    // A tab can remain open longer than the 15-minute access-token lifetime.
    // Being marked authenticated is not enough: an expired in-memory token
    // must be renewed before the next protected request is replayed.
    if (this.isAuthenticated() && !this.tokens.isAccessExpired()) return true;
    if (!this.tokens.hasSession) {
      this._user.set(null);
      this._status.set('anonymous');
      return false;
    }
    // The access token lives only in memory, so every tab that boots must
    // refresh — and refresh tokens rotate. Two tabs booting together would
    // present the same cookie twice, which the server treats as a race only
    // inside a short grace window. A cross-tab lock makes them take turns.
    const locks = (navigator as Navigator & { locks?: LockManager }).locks;
    if (locks) {
      return locks.request('vs.session-restore', () => this.restoreSessionUnlocked());
    }
    return this.restoreSessionUnlocked();
  }

  private async restoreSessionUnlocked(): Promise<boolean> {
    if (this.isAuthenticated() && !this.tokens.isAccessExpired()) return true;
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
          const retryAfter = Number(err instanceof HttpErrorResponse ? err.error?.errors?.retry_after : 0);
          await new Promise((r) => setTimeout(r, Math.min(Math.max(retryAfter, 1), 15) * 1000));
          continue;
        }
        // Only a rejected token means the session is gone. Anything else
        // (rate limit, network, server error) keeps the marker so the next
        // navigation can try again instead of forcing a new sign-in.
        if (status === 401 || status === 403) {
          this.tokens.dropAccessToken();
          this._user.set(null);
          this._status.set('anonymous');
          return false;
        }
        // Cannot reach the server: stay signed in with the last known profile
        // and keep trying, rather than showing the sign-in screen.
        return this.enterOffline();
      }
    }
  }

  private enterOffline(): boolean {
    if (!this.tokens.hasSession) return false;
    const cached = this.tokens.cachedProfile<User>();
    if (!cached?.user) return false;
    if (!this._user()) this.bootedOffline = true;
    this._user.set(cached.user);
    this.cachedScopes.set(cached.scopes ?? []);
    this._status.set('authenticated');
    this.offline.set(true);
    this.startReconnecting();
    return true;
  }

  private startReconnecting(): void {
    if (this.reconnectTimer || typeof window === 'undefined') return;
    const retry = () => void this.reconnect();
    window.addEventListener('online', retry);
    document.addEventListener('visibilitychange', retry);
    this.reconnectTimer = setInterval(retry, 15_000);
    this.stopReconnecting = () => {
      window.removeEventListener('online', retry);
      document.removeEventListener('visibilitychange', retry);
      if (this.reconnectTimer) clearInterval(this.reconnectTimer);
      this.reconnectTimer = null;
    };
  }

  private stopReconnecting: () => void = () => undefined;
  private reconnecting = false;

  /** Try the server again (also the banner's "Retry"). */
  async reconnect(): Promise<void> {
    if (!this.offline() || this.reconnecting) return;
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
    this.reconnecting = true;
    try {
      await firstValueFrom(this.refresh());
      await firstValueFrom(this.loadCurrentUser());
      this.offline.set(false);
      this.stopReconnecting();
      // Opened while offline: nothing on screen was loaded, so start fresh.
      if (this.bootedOffline && typeof window !== 'undefined') window.location.reload();
    } catch (err) {
      const status = err instanceof HttpErrorResponse ? err.status : 0;
      if (status === 401 || status === 403) {
        this.offline.set(false);
        this.stopReconnecting();
        await this.redirectToLoginAfterExpiry();
      }
    } finally {
      this.reconnecting = false;
    }
  }

  /** A refresh token was definitively rejected: clear local state and sign in again. */
  async redirectToLoginAfterExpiry(): Promise<void> {
    const returnUrl = this.router.url.startsWith('/auth') ? '/app/dashboard' : this.router.url;
    this.tokens.clear();
    this._user.set(null);
    this._status.set('anonymous');
    this.channel?.postMessage({ type: 'logout' });
    if (!this.router.url.startsWith('/auth')) {
      await this.router.navigate(['/auth/login'], {
        queryParams: { returnUrl, reason: 'session_expired' },
      });
    }
  }
}

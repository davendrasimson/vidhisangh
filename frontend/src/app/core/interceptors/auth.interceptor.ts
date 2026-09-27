import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Observable, catchError, from, switchMap, throwError } from 'rxjs';
import { TokenService } from '@core/auth/token.service';
import { AuthService } from '@core/auth/auth.service';

/** Requests to these paths must not carry a bearer token / trigger refresh. */
const AUTH_FREE = ['/auth/login', '/auth/register', '/auth/refresh'];

// Single in-flight refresh shared across concurrent 401s (avoids a stampede).
let refreshInFlight: Promise<string | null> | null = null;

/**
 * Attaches the access token and transparently refreshes it once on a 401,
 * then replays the original request with the new token.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const tokens = inject(TokenService);
  const auth = inject(AuthService);

  const isAuthFree = AUTH_FREE.some((p) => req.url.includes(p));
  const withAuth = (token: string | null) =>
    token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  const first$ = next(withAuth(isAuthFree ? null : tokens.accessToken()));

  if (isAuthFree) return first$;

  return first$.pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status !== 401) return throwError(() => err);

      if (!refreshInFlight) {
        refreshInFlight = auth
          .restoreSession()
          .then((ok) => (ok ? tokens.accessToken() : null))
          .finally(() => {
            // Reset after the microtask so queued 401s reuse this result.
            setTimeout(() => (refreshInFlight = null), 0);
          });
      }

      return from(refreshInFlight).pipe(
        switchMap((token): Observable<never> | ReturnType<typeof next> => {
          if (!token) return throwError(() => err);
          return next(withAuth(token));
        }),
      );
    }),
  );
};

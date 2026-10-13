import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '@core/auth/auth.service';
import { isNativeApp } from '@core/platform/platform';

/**
 * The public landing page is for visitors. Signed-in members (and the mobile
 * app, which has no marketing page) go straight to their dashboard.
 */
export const landingGuard: CanActivateFn = async () => {
  const router = inject(Router);
  const auth = inject(AuthService);
  if (isNativeApp()) return router.createUrlTree(['/app/dashboard']);
  if (await auth.restoreSession()) return router.createUrlTree(['/app/dashboard']);
  return true;
};

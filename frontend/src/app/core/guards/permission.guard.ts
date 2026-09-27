import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '@core/auth/auth.service';
import { NotificationService } from '@core/services/notification.service';

/**
 * Route guard factory enforcing RBAC. Usage:
 *   { path: 'billing', canActivate: [authGuard, permissionGuard('billing:manage')] }
 */
export function permissionGuard(...codes: string[]): CanActivateFn {
  return async () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    const notify = inject(NotificationService);

    await auth.restoreSession();
    const allowed = codes.every((c) => auth.hasPermission(c));
    if (allowed) return true;

    notify.error('You do not have permission to access that area.');
    return router.createUrlTree(['/app/dashboard']);
  };
}

import { HttpContextToken, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { NotificationService } from '@core/services/notification.service';
import { problemMessage } from '@core/http/problem-message';

export { problemMessage };

/**
 * Set on requests whose failure the caller reports itself (background
 * autosave shows "Could not save" in its own status line) — no toast.
 *   http.patch(url, body, { context: new HttpContext().set(SILENT_ERRORS, true) })
 */
export const SILENT_ERRORS = new HttpContextToken<boolean>(() => false);

/**
 * Surfaces API errors as user-facing notifications while re-throwing so callers
 * can still react. 401s are handled by the auth interceptor and passed through
 * quietly here.
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const notify = inject(NotificationService);

  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      // status 0 = the request never got an answer. In the background (phone
      // asleep, app minimised) that is the OS cutting the network, not news
      // for the user; the screen reloads its data when it is shown again.
      const backgroundDrop = err.status === 0 && typeof document !== 'undefined' && document.visibilityState === 'hidden';
      if (err.status !== 401 && !req.context.get(SILENT_ERRORS) && !backgroundDrop) {
        notify.error(extractMessage(err));
      }
      return throwError(() => err);
    }),
  );
};

function extractMessage(err: HttpErrorResponse): string {
  return problemMessage(err, err.message || 'An unexpected error occurred.');
}

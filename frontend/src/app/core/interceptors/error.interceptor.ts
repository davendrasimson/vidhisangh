import { HttpContextToken, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { NotificationService } from '@core/services/notification.service';
import { ApiProblem } from '@core/models/auth.models';

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
      if (err.status !== 401 && !req.context.get(SILENT_ERRORS)) {
        notify.error(extractMessage(err));
      }
      return throwError(() => err);
    }),
  );
};

function extractMessage(err: HttpErrorResponse): string {
  if (err.status === 0) return 'Cannot reach the server. Check your connection.';
  const problem = err.error as ApiProblem | undefined;
  if (problem?.detail) return problem.detail;
  return err.message || 'An unexpected error occurred.';
}

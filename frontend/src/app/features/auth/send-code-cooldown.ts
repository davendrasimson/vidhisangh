import { signal } from '@angular/core';
import type { HttpErrorResponse } from '@angular/common/http';

/**
 * An email the server will accept. Angular's `Validators.email` allows
 * "name@gmail" (no dot in the domain), which the API rejects, so sign-up
 * forms add this pattern to catch it before submitting.
 */
export const STRICT_EMAIL = /^\s*[^\s@]+@[^\s@.]+(\.[^\s@.]+)+\s*$/;

/**
 * Countdown after a WhatsApp code is sent. The server allows one code per
 * number a minute; without a visible countdown people tap "Send" again,
 * get "Too many requests" and give up.
 */
export class SendCodeCooldown {
  readonly seconds = signal(0);
  private timer: ReturnType<typeof setInterval> | null = null;

  start(seconds = 60): void {
    this.seconds.set(seconds);
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => {
      const left = this.seconds() - 1;
      this.seconds.set(Math.max(left, 0));
      if (left <= 0 && this.timer) { clearInterval(this.timer); this.timer = null; }
    }, 1000);
  }

  /** After a 429, count down the wait the server asked for (at most an hour). */
  fromError(err: unknown): void {
    const http = err as HttpErrorResponse;
    const wait = (http?.error?.errors as { retry_after?: number } | undefined)?.retry_after;
    if (http?.status === 429 && wait) this.start(Math.min(wait, 3600));
  }
}

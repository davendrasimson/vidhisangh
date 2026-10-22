import { Capacitor, registerPlugin } from '@capacitor/core';
import { isNativeApp } from './platform';
import { ReviewState, countLaunchAndDecide } from './review-rules';

/**
 * Ask a regular user, now and then, to rate the app on the Play Store / App
 * Store (the store's own sheet; the store decides whether it actually shows).
 *
 * Only after the app has been used for a while: at least MIN_DAYS since it was
 * first opened, at least MIN_LAUNCHES launches, signed in, and not more often
 * than every GAP_DAYS. Older app builds without the plugin skip it (live screen
 * updates reach them too), and so does iOS for now.
 */
const KEY = 'vs_review_prompt';
/** The app's own plugin (android/.../InAppReviewPlugin.java); absent on iOS and older builds. */
const InAppReview = registerPlugin<{ requestReview(): Promise<void> }>('InAppReview');

export async function maybeAskForReview(signedIn: boolean): Promise<void> {
  if (!isNativeApp() || !signedIn || !Capacitor.isPluginAvailable('InAppReview')) return;
  let saved: ReviewState | null = null;
  try { saved = JSON.parse(localStorage.getItem(KEY) ?? 'null'); } catch { /* start afresh */ }
  const { state, ask } = countLaunchAndDecide(saved, Date.now());
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* storage unavailable: never ask */ return; }
  if (!ask) return;
  try {
    await InAppReview.requestReview();
  } catch { /* the store said no; try again after the gap */ }
}

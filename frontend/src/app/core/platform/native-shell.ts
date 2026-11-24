import { ApplicationRef, NgZone } from '@angular/core';
import { Router } from '@angular/router';
import { isNativeApp } from './platform';
import { initLiveUpdates } from './live-update';
import { initPush } from './push';
import { appLinkPath } from './app-links';
import { maybeAskForReview } from './review-prompt';
import { AuthService } from '@core/auth/auth.service';

/** Screens where the Android back button leaves the app instead of going back. */
const ROOT_PATHS = new Set(['/', '/app', '/app/dashboard', '/auth/login']);

/**
 * One-time setup when running inside the Android / iOS app. A no-op in browsers.
 *
 * - Safe area (status bar, notch, gesture bar): `index.html` deliberately has no
 *   `viewport-fit=cover`. Capacitor's SystemBars reads the viewport once at page
 *   load; without `cover` it pads the WebView natively on every WebView version.
 *   With `cover` and WebView 140+ it leaves the insets to page CSS, and the page ran
 *   under both bars (seen on a phone, 13 Oct 2026). iOS is the opposite case: the
 *   web view always runs under the status bar there, so `viewport-fit=cover` is set
 *   at runtime on iOS only and the shell pads with `env(safe-area-inset-top)`.
 * - Android back button: go back through the app's own history; on a root
 *   screen, leave the app. The WebView's own `canGoBack` is not trusted here:
 *   Chromium marks history entries created without a tap as skippable, so it
 *   can report "nothing to go back to" while the app has screens behind it.
 * - Hide the splash screen once Angular has rendered.
 * - Live screen updates from vidhisangh.com (live-update.ts).
 * - Push notifications after sign-in (push.ts).
 * - vidhisangh.com links opened from WhatsApp, email etc. (app-links.ts): go to
 *   that screen, both when they start the app and when it is already running.
 * - Now and then, a store rating request (review-prompt.ts).
 */
export async function initNativeShell(appRef: ApplicationRef): Promise<void> {
  if (!isNativeApp()) return;
  document.documentElement.classList.add('vs-native');
  // iPhone only: the web view runs under the status bar (capacitor.config.ts `contentInset: 'never'`),
  // and WebKit reports `env(safe-area-inset-*)` only when the viewport asks for `viewport-fit=cover`.
  // Set it at runtime so Android keeps the native padding described above (24 Nov 2026: the top bar
  // sat under the clock and battery in every TestFlight recording).
  const { Capacitor } = await import('@capacitor/core');
  if (Capacitor.getPlatform() === 'ios') {
    document.querySelector('meta[name="viewport"]')?.setAttribute('content', 'width=device-width, initial-scale=1, viewport-fit=cover');
  }

  const router = appRef.injector.get(Router);
  const [{ App }, { SplashScreen }] = await Promise.all([
    import('@capacitor/app'),
    import('@capacitor/splash-screen'),
  ]);
  await App.addListener('backButton', ({ canGoBack }) => {
    const path = router.url.split(/[?#]/)[0];
    if (ROOT_PATHS.has(path)) {
      void App.exitApp();
    } else if (canGoBack || window.history.length > 1) {
      window.history.back();
    } else {
      void router.navigateByUrl('/app/dashboard');
    }
  });
  await App.addListener('appUrlOpen', ({ url }) => {
    const path = appLinkPath(url);
    if (path) void appRef.injector.get(NgZone).run(() => router.navigateByUrl(path));
  });
  // Angular has started: confirm these screens before anything else can fail.
  await initLiveUpdates();
  await SplashScreen.hide({ fadeOutDuration: 200 });
  await initPush(appRef);
  // Now and then, once the app is in regular use: the store's rating sheet.
  // Not during start-up, so it never covers the first screen.
  const auth = appRef.injector.get(AuthService);
  setTimeout(() => void maybeAskForReview(auth.isAuthenticated()), 20_000);
}

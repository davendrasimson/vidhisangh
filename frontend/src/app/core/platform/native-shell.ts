import { ApplicationRef } from '@angular/core';
import { Router } from '@angular/router';
import { isNativeApp } from './platform';

/** Screens where the Android back button leaves the app instead of going back. */
const ROOT_PATHS = new Set(['/', '/app', '/app/dashboard', '/auth/login']);

/**
 * One-time setup when running inside the Android / iOS app. A no-op in browsers.
 *
 * - Safe area (status bar, notch, gesture bar): `index.html` deliberately has no
 *   `viewport-fit=cover`. Capacitor's SystemBars reads the viewport once at page
 *   load; without `cover` it pads the WebView natively on every WebView version.
 *   With `cover` and WebView 140+ it leaves the insets to page CSS we don't have,
 *   and the page ran under both bars (seen on a phone, 13 Oct 2026).
 * - Android back button: go back through the app's own history; on a root
 *   screen, leave the app. The WebView's own `canGoBack` is not trusted here:
 *   Chromium marks history entries created without a tap as skippable, so it
 *   can report "nothing to go back to" while the app has screens behind it.
 * - Hide the splash screen once Angular has rendered.
 */
export async function initNativeShell(appRef: ApplicationRef): Promise<void> {
  if (!isNativeApp()) return;
  document.documentElement.classList.add('vs-native');

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
  await SplashScreen.hide({ fadeOutDuration: 200 });
}

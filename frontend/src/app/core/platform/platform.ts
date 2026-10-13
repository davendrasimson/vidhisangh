import { Capacitor } from '@capacitor/core';
import { environment } from '@env/environment';

/** True inside the Android / iOS app (Capacitor), false in any browser. */
export function isNativeApp(): boolean {
  return Capacitor.isNativePlatform();
}

/**
 * Origin for links people open outside the app: payment links, portal links,
 * judgment links in a memo. Inside the app `location.origin` is the device's
 * own `https://localhost`, which nobody else can open.
 */
export function publicOrigin(): string {
  return environment.publicAppUrl || window.location.origin;
}

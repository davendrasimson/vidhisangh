import { ApplicationRef, effect } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { AuthService } from '@core/auth/auth.service';
import { isNativeApp } from './platform';

/**
 * Push notifications in the Android / iOS app (Firebase Cloud Messaging).
 *
 * After sign-in the app asks for the OS permission once (Android 13+ shows the
 * system prompt; that is the member's consent), registers with Firebase and
 * sends the device token to the server, which then pushes every in-app
 * notification to this phone. Tapping a notification opens its screen. At
 * sign-out the token is removed so the next person on this phone gets nothing
 * meant for the last one. A no-op in browsers.
 */
let deviceToken: string | null = null;
let platform: 'android' | 'ios' = 'android';

export async function initPush(appRef: ApplicationRef): Promise<void> {
  if (!isNativeApp()) return;
  const injector = appRef.injector;
  const auth = injector.get(AuthService);
  const http = injector.get(HttpClient);
  const router = injector.get(Router);
  try {
    const [{ PushNotifications }, { Capacitor }] = await Promise.all([
      import('@capacitor/push-notifications'),
      import('@capacitor/core'),
    ]);
    platform = Capacitor.getPlatform() === 'ios' ? 'ios' : 'android';
    if (platform === 'android') {
      await PushNotifications.createChannel({
        id: 'default', name: 'Notifications', description: 'Connection requests, replies and hearing alerts',
        importance: 4, visibility: 1,
      }).catch(() => undefined);
    }
    await PushNotifications.addListener('registration', ({ value }) => {
      deviceToken = value;
      void sendToken(http, auth);
    });
    await PushNotifications.addListener('pushNotificationActionPerformed', ({ notification }) => {
      const link = String(notification.data?.link ?? '/app/notifications');
      void router.navigateByUrl(link.startsWith('/') && !link.startsWith('//') ? link : '/app/notifications');
    });

    let asked = false;
    effect(() => {
      if (!auth.user() || asked) return;
      asked = true;
      void (async () => {
        let status = (await PushNotifications.checkPermissions()).receive;
        if (status === 'prompt' || status === 'prompt-with-rationale') {
          status = (await PushNotifications.requestPermissions()).receive;
        }
        if (status === 'granted') await PushNotifications.register();
      })().catch(() => undefined);
    }, { injector });
  } catch {
    /* plugin missing (older app build) or Firebase not set up: no push */
  }
}

async function sendToken(http: HttpClient, auth: AuthService): Promise<void> {
  if (!deviceToken || !auth.user()) return;
  try {
    await firstValueFrom(http.post(`${environment.apiBaseUrl}/notifications/devices`, { token: deviceToken, platform }));
  } catch { /* retried on the next app start */ }
}

/** At sign-out, before the session ends: stop push to this phone. */
export async function forgetPushDevice(http: HttpClient): Promise<void> {
  if (!deviceToken) return;
  try {
    await firstValueFrom(http.post(`${environment.apiBaseUrl}/notifications/devices/remove`, { token: deviceToken, platform }));
  } catch { /* best effort */ }
}

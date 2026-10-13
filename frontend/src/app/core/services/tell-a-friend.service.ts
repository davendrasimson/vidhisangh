import { Injectable, inject } from '@angular/core';
import { NotificationService } from '@core/services/notification.service';
import { isNativeApp } from '@core/platform/platform';

const SITE_URL = 'https://vidhisangh.com/?utm_source=tell_a_friend';
const PLAY_URL = 'https://play.google.com/store/apps/details?id=com.vidhisangh.app';

const TITLE = 'Join me on VidhiSangh';
const TEXT =
  "I'm on VidhiSangh, the free professional network for India's legal fraternity — " +
  'advocates, judges, researchers, law students and firms. Search millions of judgments ' +
  'and read BNS, BNSS and BSA free.\n\n' +
  `Android app: ${PLAY_URL}\nOn the web:`;

/**
 * "Tell a friend": the phone's share sheet in the app, the browser's share
 * sheet where it exists, otherwise the invite is copied to the clipboard.
 * The links are fixed public addresses, so they work for anyone who gets them.
 */
@Injectable({ providedIn: 'root' })
export class TellAFriendService {
  private readonly notify = inject(NotificationService);

  async share(): Promise<void> {
    try {
      if (isNativeApp()) {
        const { Share } = await import('@capacitor/share');
        await Share.share({ title: TITLE, text: TEXT, url: SITE_URL, dialogTitle: 'Tell a friend' });
        return;
      }
      if (navigator.share) {
        await navigator.share({ title: TITLE, text: TEXT, url: SITE_URL });
        return;
      }
      await navigator.clipboard.writeText(`${TEXT} ${SITE_URL}`);
      this.notify.success('Invite copied — paste it into WhatsApp, email or a message.');
    } catch (err) {
      // Closing the share sheet is not an error worth reporting.
      const name = (err as { name?: string; message?: string })?.name ?? '';
      const message = (err as { message?: string })?.message ?? '';
      if (name === 'AbortError' || /cancel/i.test(message)) return;
      this.notify.error('Could not open sharing. Copy vidhisangh.com and send it to your friend.');
    }
  }
}

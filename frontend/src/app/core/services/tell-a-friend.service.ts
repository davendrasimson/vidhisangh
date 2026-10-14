import { HttpClient, HttpContext } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { SILENT_ERRORS } from '@core/interceptors/error.interceptor';
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

export interface MyReferral {
  code: string;
  link: string;
  joined: number;
}

/**
 * "Tell a friend": the phone's share sheet in the app, the browser's share
 * sheet where it exists, otherwise the invite is copied to the clipboard.
 * The link is the user's personal invite link (vidhisangh.com/?ref=CODE), so
 * people who sign up through it are counted for them; if it cannot be fetched,
 * the plain site address is shared instead.
 */
@Injectable({ providedIn: 'root' })
export class TellAFriendService {
  private readonly notify = inject(NotificationService);
  private readonly http = inject(HttpClient);
  /** The signed-in user's invite link and how many joined through it. */
  readonly referral = signal<MyReferral | null>(null);

  async loadReferral(): Promise<MyReferral | null> {
    try {
      const mine = await firstValueFrom(this.http.get<MyReferral>(`${environment.apiBaseUrl}/referrals/me`, {
        context: new HttpContext().set(SILENT_ERRORS, true),
      }));
      this.referral.set(mine);
      return mine;
    } catch {
      return null;
    }
  }

  async share(): Promise<void> {
    const link = (this.referral() ?? (await this.loadReferral()))?.link ?? SITE_URL;
    return this.shareLink(TITLE, TEXT, link, 'Tell a friend');
  }

  /** Share any public link the same way: share sheet, else clipboard. */
  async shareLink(title: string, text: string, url: string, dialogTitle = 'Share'): Promise<void> {
    try {
      if (isNativeApp()) {
        const { Share } = await import('@capacitor/share');
        await Share.share({ title, text, url, dialogTitle });
        return;
      }
      if (navigator.share) {
        await navigator.share({ title, text, url });
        return;
      }
      await navigator.clipboard.writeText(`${text} ${url}`);
      this.notify.success('Link copied — paste it into WhatsApp, email or a message.');
    } catch (err) {
      // Closing the share sheet is not an error worth reporting.
      const name = (err as { name?: string; message?: string })?.name ?? '';
      const message = (err as { message?: string })?.message ?? '';
      if (name === 'AbortError' || /cancel/i.test(message)) return;
      this.notify.error(`Could not open sharing. Copy this link instead: ${url}`);
    }
  }
}

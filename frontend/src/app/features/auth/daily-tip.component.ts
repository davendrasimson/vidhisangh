import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/** One short product tip per day, under the sign-in and sign-up forms. */
export const PRODUCT_TIPS: readonly string[] = [
  'Read BNS, BNSS and BSA section by section, free, with the matching old IPC, CrPC or Evidence Act section on each page.',
  'Sign in with a WhatsApp code: no password to remember. Your number is enough.',
  'Search Supreme Court and High Court judgments by party, advocate, judge, Act or section, with Google-style quotes and minus signs.',
  'Invite colleagues with your personal link (Tell a friend). You can see how many joined through you.',
  'Add a hearing to a matter and it shows on your calendar, with the next date on the matter list.',
  'Share a KYC link with a client: they fill in and confirm their own details, and you review them.',
  'Draft notices and petitions in English, Hindi or Punjabi, then export them to Word.',
  'Send a document for e-signature and download the signed copy with its certificate.',
  'Record time against a matter, get it approved, and turn it into a GST invoice in a few clicks.',
  'Join or start a group for your bar association, court or law college to share updates in one place.',
  'Message other members directly. Connection requests and replies arrive as notifications.',
  'Choose who sees your role on your profile: everyone, only your connections, or nobody.',
  'Read legal news from official sources in the News section, updated through the day.',
  'Give your client a portal link to follow their matter without calling you for every update.',
  'Lost the signal? The app keeps you signed in and reconnects by itself.',
  'Tap the bulb (top right) for a short guide to the page you are on.',
  '21 central Acts are free to read on vidhisangh.com/acts, including the CPC, Contract Act and IT Act.',
  'Open a case in Research to see all its orders in date order, with the parties and counsel.',
  'Use the timesheet import to bring a month of entries in from Excel at once.',
  'Record the limitation date on each matter so the deadline is always in front of you.',
  'VidhiSangh is free for the legal fraternity: advocates, judges, researchers, law students, munshi and law firms.',
];

function istDayNumber(now = new Date()): number {
  // Day count in India time, so the tip changes at midnight IST.
  return Math.floor((now.getTime() + 5.5 * 3600 * 1000) / 86_400_000);
}

@Component({
  selector: 'app-daily-tip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <aside class="mt-6 rounded-xl border border-line bg-surface-raised p-4" aria-label="Tip of the day">
      <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand">
        <mat-icon class="material-icons-outlined !text-base !w-4 !h-4" aria-hidden="true">lightbulb</mat-icon>
        Tip of the day
        <span class="flex-1"></span>
        <button type="button" class="normal-case font-medium text-content-muted hover:text-brand" (click)="offset.set(offset() + 1)">Next tip</button>
      </div>
      <p class="mt-2 text-sm leading-relaxed text-content">{{ tip() }}</p>
    </aside>
  `,
})
export class DailyTipComponent {
  protected readonly offset = signal(0);
  protected readonly tip = computed(() => PRODUCT_TIPS[(istDayNumber() + this.offset()) % PRODUCT_TIPS.length]);
}

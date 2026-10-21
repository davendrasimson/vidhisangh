import { ChangeDetectionStrategy, Component, OnInit, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { NotificationService } from '@core/services/notification.service';
import { TellAFriendService, whatsappInvite } from '@core/services/tell-a-friend.service';

/**
 * "Invite colleagues" on the member's own profile: how many joined through
 * their personal link, progress to the Founding Member badge, and one-tap
 * WhatsApp / share / copy of the link.
 */
@Component({
  selector: 'vs-invite-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatIconModule],
  template: `
    @if (referral(); as r) {
      <section class="profile-card">
        <h2>Invite colleagues</h2>
        @if (r.founding_member) {
          <p class="text-sm"><span class="vs-chip text-xs mr-1">★ Founding Member</span> {{ r.joined }} colleagues joined through your link. Thank you!</p>
        } @else {
          <p class="text-sm text-content-muted">
            {{ r.joined === 0 ? 'Nobody has joined through your link yet.' : r.joined + (r.joined === 1 ? ' colleague has' : ' colleagues have') + ' joined through your link.' }}
            Invite {{ remaining() }} more to earn the <strong>Founding Member</strong> badge on your profile.
          </p>
          <div class="h-2 rounded-full bg-line overflow-hidden my-2" role="progressbar" [attr.aria-valuenow]="r.joined" aria-valuemin="0" [attr.aria-valuemax]="goal()">
            <div class="h-full bg-brand" [style.width.%]="progress()"></div>
          </div>
        }
        <div class="flex flex-wrap gap-2 mt-2">
          <a mat-flat-button class="!bg-[#1f9d55] !text-white" [href]="whatsapp()" target="_blank" rel="noopener">
            <mat-icon class="material-icons-outlined">chat</mat-icon> Invite on WhatsApp
          </a>
          <button mat-stroked-button type="button" (click)="share()"><mat-icon class="material-icons-outlined">share</mat-icon> Share</button>
          <button mat-stroked-button type="button" (click)="copy(r.link)"><mat-icon class="material-icons-outlined">content_copy</mat-icon> Copy link</button>
        </div>
      </section>
    }
  `,
})
export class InviteCardComponent implements OnInit {
  private readonly invites = inject(TellAFriendService);
  private readonly notify = inject(NotificationService);
  protected readonly referral = this.invites.referral;
  protected readonly goal = computed(() => this.referral()?.founding_goal ?? 3);
  protected readonly remaining = computed(() => Math.max(0, this.goal() - (this.referral()?.joined ?? 0)));
  protected readonly progress = computed(() => Math.min(100, ((this.referral()?.joined ?? 0) / this.goal()) * 100));
  protected readonly whatsapp = computed(() => whatsappInvite(this.referral()?.link ?? 'https://vidhisangh.com/'));

  ngOnInit(): void {
    void this.invites.loadReferral();
  }

  protected share(): Promise<void> {
    return this.invites.share();
  }

  protected async copy(link: string): Promise<void> {
    try { await navigator.clipboard.writeText(link); this.notify.success('Invite link copied.'); } catch { /* clipboard unavailable */ }
  }
}

import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { environment } from '@env/environment';
import { AuthService } from '@core/auth/auth.service';
import { problemMessage } from '@core/http/problem-message';
import { rememberGroupInvite } from '@core/groups/pending-invite';
import { PublicFooterComponent, PublicHeaderComponent } from '@shared/public-chrome/public-chrome.component';

interface InvitePreview { group_id: string; name: string; description: string | null; member_count: number; is_verified: boolean }

/**
 * /join/:code — a group's invite link (bar associations, law colleges).
 * Signed in: one tap joins. New: sign up first; the invite is remembered and
 * joined on arrival in the app (core/groups/pending-invite.ts).
 */
@Component({
  selector: 'app-join-group',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatButtonModule, PublicHeaderComponent, PublicFooterComponent],
  template: `
    <vs-public-header />
    <main class="min-h-[60vh] grid place-items-center px-4 py-12 bg-surface-sunken">
      <section class="w-full max-w-md rounded-card border border-line bg-surface-raised p-6 text-center shadow-card">
        @if (preview(); as g) {
          <p class="text-xs font-bold uppercase tracking-wide text-brand">Invitation to a group</p>
          <h1 class="text-2xl font-bold text-content mt-1">{{ g.name }} @if (g.is_verified) { <span class="text-brand text-base" title="Verified">✓</span> }</h1>
          @if (g.description) { <p class="mt-2 text-content-muted">{{ g.description }}</p> }
          <p class="mt-1 text-sm text-content-muted">{{ g.member_count }} member{{ g.member_count === 1 ? '' : 's' }} on VidhiSangh</p>
          @if (error()) { <p role="alert" class="mt-3 text-danger text-sm">{{ error() }}</p> }
          @if (auth.user()) {
            <button mat-flat-button color="primary" class="mt-5 w-full h-11" [disabled]="busy()" (click)="join(g)">{{ busy() ? 'Joining…' : 'Join the group' }}</button>
          } @else {
            <a mat-flat-button color="primary" class="mt-5 w-full h-11" routerLink="/auth/register" [queryParams]="{ utm_source: 'group_invite' }" (click)="remember()">Join VidhiSangh free to join</a>
            <a mat-button class="mt-2 w-full" routerLink="/auth/login" [queryParams]="{ returnUrl: '/join/' + code }" (click)="remember()">I have an account — sign in</a>
            <p class="mt-3 text-xs text-content-muted">You'll be added to the group as soon as you're in.</p>
          }
        } @else if (missing()) {
          <h1 class="text-2xl font-bold text-content">This invite link has expired</h1>
          <p class="mt-2 text-content-muted">Ask the group's admin for a new link, or find the group on VidhiSangh.</p>
          <a mat-flat-button color="primary" class="mt-5" routerLink="/">VidhiSangh home</a>
        } @else {
          <p class="text-content-muted">Loading…</p>
        }
      </section>
    </main>
    <vs-public-footer />
  `,
})
export class JoinGroupComponent implements OnInit {
  protected readonly auth = inject(AuthService);
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  protected readonly code = inject(ActivatedRoute).snapshot.paramMap.get('code') ?? '';
  protected readonly preview = signal<InvitePreview | null>(null);
  protected readonly missing = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    if (typeof window === 'undefined') return;  // not prerendered: each code is different
    try {
      this.preview.set(await firstValueFrom(this.http.get<InvitePreview>(`${environment.apiBaseUrl}/groups/invite/${encodeURIComponent(this.code)}`)));
    } catch { this.missing.set(true); }
  }

  protected remember(): void {
    rememberGroupInvite(this.code);
  }

  protected async join(g: InvitePreview): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await firstValueFrom(this.http.post(`${environment.apiBaseUrl}/groups/invite/${encodeURIComponent(this.code)}/join`, {}));
      await this.router.navigate(['/app/groups', g.group_id]);
    } catch (err) {
      this.error.set(problemMessage(err, 'Could not join. Please try again.'));
    } finally { this.busy.set(false); }
  }
}

import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { PublicFooterComponent, PublicHeaderComponent } from '@shared/public-chrome/public-chrome.component';

/**
 * /unsubscribe/:token: the link at the foot of every invitation email.
 * One tap confirms. Not automatic on page load: mail security scanners open
 * links before people do (see the verify-email fix), and would unsubscribe
 * everyone. The mail apps' own Unsubscribe button (List-Unsubscribe) is
 * one-click with no page at all.
 */
@Component({
  selector: 'app-unsubscribe',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PublicHeaderComponent, PublicFooterComponent],
  template: `
    <vs-public-header />
    <main class="min-h-[60vh] grid place-items-center px-4 py-12 bg-surface-sunken">
      <section class="w-full max-w-md rounded-card border border-line bg-surface-raised p-6 text-center shadow-card">
        @if (state() === 'done') {
          <h1 class="text-2xl font-bold text-content">You're unsubscribed</h1>
          <p class="mt-2 text-content-muted">We will not send you any more invitation emails. Your address is on our do-not-email list.</p>
        } @else {
          <h1 class="text-2xl font-bold text-content">Stop VidhiSangh invitation emails?</h1>
          <p class="mt-2 text-content-muted">We'll remove your address and never email it again.</p>
          @if (state() === 'error') { <p role="alert" class="mt-3 text-danger text-sm">That didn't go through. Please try again.</p> }
          <button type="button" class="mt-5 w-full rounded-full bg-brand px-5 py-3 font-semibold text-white disabled:opacity-60"
                  [disabled]="state() === 'working'" (click)="confirm()">
            {{ state() === 'working' ? 'Unsubscribing…' : 'Unsubscribe' }}
          </button>
        }
      </section>
    </main>
    <vs-public-footer />
  `,
})
export class UnsubscribeComponent {
  private readonly http = inject(HttpClient);
  private readonly token = inject(ActivatedRoute).snapshot.paramMap.get('token') ?? '';
  protected readonly state = signal<'ready' | 'working' | 'done' | 'error'>('ready');

  protected async confirm(): Promise<void> {
    this.state.set('working');
    try {
      await firstValueFrom(this.http.post(`${environment.apiBaseUrl}/outreach/unsubscribe/${encodeURIComponent(this.token)}`, {}));
      this.state.set('done');
    } catch {
      this.state.set('error');
    }
  }
}

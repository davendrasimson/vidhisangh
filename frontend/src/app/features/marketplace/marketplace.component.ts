import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { ActivatedRoute } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MarketplaceService } from '@core/services/marketplace.service';
import { NotificationService } from '@core/services/notification.service';
import { Listing, ListingResponse, ListingType } from '@core/models/marketplace.models';

type Tab = 'browse' | 'mine';

@Component({
  selector: 'app-marketplace',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, MatIconModule, MatButtonModule],
  templateUrl: './marketplace.component.html',
})
export class MarketplaceComponent implements OnInit {
  private readonly market = inject(MarketplaceService);
  private readonly notify = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);

  protected readonly tab = signal<Tab>('browse');
  protected readonly listings = signal<Listing[]>([]);
  protected readonly loading = signal(true);
  protected readonly type = signal<ListingType | ''>('');
  protected search = '';

  // Per-listing UI state.
  protected readonly replyOpen = signal<Record<string, boolean>>({});
  protected replyDraft: Record<string, string> = {};
  protected readonly responses = signal<Record<string, ListingResponse[] | undefined>>({});

  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected form = this.blank();

  protected readonly types: { value: ListingType | ''; label: string }[] = [
    { value: '', label: 'All' },
    { value: 'referral', label: 'Referrals' },
    { value: 'local_counsel', label: 'Local counsel' },
    { value: 'expert', label: 'Experts' },
    { value: 'researcher', label: 'Researchers' },
    { value: 'arbitrator', label: 'Arbitrators' },
    { value: 'job', label: 'Jobs' },
    { value: 'internship', label: 'Internships' },
  ];

  async ngOnInit(): Promise<void> {
    const q = this.route.snapshot.queryParamMap;
    if (q.get('matter_id')) {
      this.form.matter_id = q.get('matter_id');
      this.form.title = `Local counsel / expert for ${q.get('matter_title') || 'matter'}`;
      this.form.practice_area = q.get('practice_area') || '';
      this.form.type = 'local_counsel';
      this.showForm.set(true);
    }
    await this.load();
  }

  protected async switchTab(tab: Tab): Promise<void> {
    if (this.tab() === tab) return;
    this.tab.set(tab);
    await this.load();
  }

  protected async setType(t: ListingType | ''): Promise<void> {
    this.type.set(t);
    await this.load();
  }

  protected async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.listings.set(
        this.tab() === 'mine'
          ? await firstValueFrom(this.market.mine())
          : await firstValueFrom(this.market.browse({ type: this.type(), q: this.search.trim() })),
      );
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected label(s: string): string {
    return s.replace('_', ' ');
  }

  // ── Respond (browse) ───────────────────────────────────────────
  protected toggleReply(l: Listing): void {
    this.replyOpen.update((r) => ({ ...r, [l.id]: !r[l.id] }));
  }

  protected async sendReply(l: Listing): Promise<void> {
    const message = (this.replyDraft[l.id] ?? '').trim();
    if (!message) return;
    try {
      await firstValueFrom(this.market.respond(l.id, message));
      this.replyDraft[l.id] = '';
      this.replyOpen.update((r) => ({ ...r, [l.id]: false }));
      this.notify.success('Response sent to the poster.');
    } catch {
      /* handled */
    }
  }

  // ── My listings ────────────────────────────────────────────────
  protected async viewResponses(l: Listing): Promise<void> {
    const open = this.responses();
    if (open[l.id] !== undefined) {
      this.responses.set({ ...open, [l.id]: undefined });
      return;
    }
    try {
      this.responses.set({ ...this.responses(), [l.id]: await firstValueFrom(this.market.responses(l.id)) });
    } catch {
      /* handled */
    }
  }

  protected async close(l: Listing): Promise<void> {
    try {
      const updated = await firstValueFrom(this.market.close(l.id));
      this.listings.update((list) => list.map((x) => (x.id === l.id ? updated : x)));
    } catch {
      /* handled */
    }
  }

  protected async accept(l: Listing, response: ListingResponse): Promise<void> {
    try {
      const updated = await firstValueFrom(this.market.accept(l.id, response.id));
      this.listings.update((items) => items.map((x) => x.id === l.id ? updated : x));
      this.notify.success(`${response.responder_name} added to the linked matter as counsel.`);
    } catch { /* handled */ }
  }

  protected async submit(): Promise<void> {
    if (!this.form.title.trim() || !this.form.description.trim() || this.saving()) return;
    this.saving.set(true);
    try {
      await firstValueFrom(
        this.market.create({
          type: this.form.type,
          title: this.form.title.trim(),
          description: this.form.description.trim(),
          practice_area: this.form.practice_area.trim() || null,
          location: this.form.location.trim() || null,
          matter_id: this.form.matter_id,
        }),
      );
      this.notify.success('Listing posted.');
      this.form = this.blank();
      this.showForm.set(false);
      this.tab.set('mine');
      await this.load();
    } catch {
      /* handled */
    } finally {
      this.saving.set(false);
    }
  }

  private blank() {
    return { type: 'referral' as ListingType, title: '', description: '', practice_area: '', location: '', matter_id: null as string | null };
  }
}

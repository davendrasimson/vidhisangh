import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { NewsService } from '@core/services/news.service';
import { NotificationService } from '@core/services/notification.service';
import { NewsCategory, NewsItem, NewsItemCreate } from '@core/models/news.models';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';

const csv = (v: string): string[] => v.split(',').map((s) => s.trim()).filter(Boolean);

@Component({
  selector: 'app-news',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [VsDateInputComponent, FormsModule, DatePipe, MatIconModule, MatButtonModule],
  templateUrl: './news.component.html',
  styleUrl: './news.component.scss',
})
export class NewsComponent implements OnInit {
  private readonly news = inject(NewsService);
  private readonly notify = inject(NotificationService);

  protected readonly items = signal<NewsItem[]>([]);
  protected readonly loading = signal(true);
  protected readonly category = signal<NewsCategory | ''>('');
  protected readonly expanded = signal<string | null>(null);
  protected readonly failedImages = signal<Set<string>>(new Set());
  protected readonly illustration = '/images/news/justice-editorial.webp';
  protected imageFailed(id: string): void {
    this.failedImages.update(ids => new Set([...ids, id]));
  }
  protected search = '';
  protected source = '';
  protected readonly sources = signal(['Supreme Court of India', 'High Court of Delhi', 'India Code', 'Legislative Department']);
  protected readonly view = signal<'cards' | 'list'>('cards');
  protected readonly more = signal(false);
  protected readonly loadingMore = signal(false);
  protected readonly error = signal(false);
  protected readonly saved = signal<Set<string>>(new Set());
  private page = 1;
  private request = 0;

  protected toggleSave(id: string): void {
    this.saved.update(ids => { const next = new Set(ids); next.has(id) ? next.delete(id) : next.add(id); return next; });
    try { localStorage.setItem('vidhisangh-news-saved', JSON.stringify([...this.saved()])); } catch { /* storage unavailable */ }
  }

  protected headline(n: NewsItem): string { return n.title.split(' - Diary Number')[0].split(' - C.A. No.')[0].split(' - Crl.A. No.')[0]; }
  protected typeLabel(n: NewsItem): string { return /pronouncement/i.test(n.title) ? 'Pronouncement schedule' : this.categories.find(c => c.value === n.category)?.label || 'Update'; }
  protected resetFilters(): void { this.search = ''; this.source = ''; this.category.set(''); void this.load(); }
  protected fallback(n: NewsItem): string {
    if (n.category === 'legislation') return '/images/news/legislation-editorial.webp';
    if (['notification', 'circular'].includes(n.category)) return '/images/news/official-notice-editorial.webp';
    return /high court/i.test(n.source) ? '/images/news/state-high-court-editorial.webp' : this.illustration;
  }

  protected readonly showAdd = signal(false);
  protected readonly saving = signal(false);
  protected addForm = this.blank();

  protected readonly categories: { value: NewsCategory | ''; label: string }[] = [
    { value: '', label: 'All' },
    { value: 'judgment', label: 'Judgments' },
    { value: 'legislation', label: 'Legislation' },
    { value: 'notification', label: 'Notifications' },
    { value: 'circular', label: 'Circulars' },
    { value: 'news', label: 'News' },
  ];

  async ngOnInit(): Promise<void> {
    try { const ids = JSON.parse(localStorage.getItem('vidhisangh-news-saved') || '[]'); if (Array.isArray(ids)) this.saved.set(new Set(ids.filter(id => typeof id === 'string'))); } catch { /* storage unavailable */ }
    await this.load();
  }

  protected async setCategory(c: NewsCategory | ''): Promise<void> {
    this.category.set(c);
    await this.load();
  }

  protected async load(append = false): Promise<void> {
    if (append && (this.loading() || this.loadingMore() || !this.more())) return;
    const request = ++this.request;
    const page = append ? this.page + 1 : 1;
    this.error.set(false);
    if (append) this.loadingMore.set(true); else { this.loading.set(true); this.loadingMore.set(false); }
    try {
      const rows = await firstValueFrom(this.news.list({ q: this.search.trim(), category: this.category(), source: this.source, page, size: 12 }));
      if (request !== this.request) return;
      this.items.update(items => append ? [...new Map([...items, ...rows].map(item => [item.id, item])).values()] : rows);
      this.sources.update(sources => [...new Set([...sources, ...rows.map(item => item.source)])]);
      this.page = page;
      this.more.set(rows.length === 12);
    } catch {
      if (request === this.request) this.error.set(true);
    } finally {
      if (request === this.request) { this.loading.set(false); this.loadingMore.set(false); }
    }
  }

  protected toggleExpanded(id: string): void { this.expanded.update((value) => value === id ? null : id); }

  protected async share(item: NewsItem): Promise<void> {
    if (!item.url) return;
    try { await navigator.clipboard.writeText(item.url); this.notify.success('Link copied.'); } catch { window.open(item.url, '_blank', 'noopener'); }
  }

  protected icon(category: NewsCategory): string {
    return ({ judgment: 'gavel', legislation: 'account_balance', notification: 'campaign', circular: 'description', news: 'newspaper' } as Record<string, string>)[category] || 'newspaper';
  }

  protected async submitAdd(): Promise<void> {
    const f = this.addForm;
    if (!f.title.trim() || !f.source.trim() || !f.published_at || this.saving()) return;
    this.saving.set(true);
    try {
      const payload: NewsItemCreate = {
        title: f.title.trim(),
        summary: f.summary.trim() || null,
        source: f.source.trim(),
        category: f.category,
        url: f.url.trim() || null,
        published_at: new Date(f.published_at).toISOString(),
        tags: csv(f.tags),
      };
      const created = await firstValueFrom(this.news.create(payload));
      this.notify.success('News item added.');
      this.addForm = this.blank();
      this.showAdd.set(false);
      await this.load();
    } catch {
      /* handled */
    } finally {
      this.saving.set(false);
    }
  }

  private blank() {
    return {
      title: '', summary: '', source: '', category: 'news' as NewsCategory,
      url: '', published_at: '', tags: '',
    };
  }
}

import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { firstValueFrom } from 'rxjs';
import { BriefService } from '@core/services/brief.service';
import { WhatsappDailyComponent } from '@shared/whatsapp-daily/whatsapp-daily.component';
import { NetworkService } from '@core/services/network.service';
import { NotificationService } from '@core/services/notification.service';
import { publicOrigin } from '@core/platform/platform';
import { Brief, BriefCardKind, BriefLead, LEAD_TITLES } from '@core/models/brief.models';
import { DailyCard, DirectoryPerson } from '@core/models/network.models';

/**
 * VidhiSangh Daily (4 Nov 2026): one page a day. The lead item comes first and
 * rotates by weekday (see backend app/modules/brief/service.py); the rest
 * follow in a fixed order. The morning push opens this page with ?from=push.
 */
@Component({
  selector: 'app-daily-brief',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, DecimalPipe, RouterLink, MatButtonModule, MatIconModule, WhatsappDailyComponent],
  templateUrl: './daily-brief.component.html',
})
export class DailyBriefComponent implements OnInit {
  private readonly briefs = inject(BriefService);
  private readonly network = inject(NetworkService);
  private readonly notify = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly brief = signal<Brief | null>(null);
  protected readonly loading = signal(true);
  protected readonly answering = signal(false);
  protected readonly connecting = signal<Set<string>>(new Set());
  protected readonly titles = LEAD_TITLES;
  private readonly origin = publicOrigin();

  /** The items in page order: the lead first, then the member's court (when their profile names one), then the rest. */
  protected readonly order = computed<BriefCardKind[]>(() => {
    const all: BriefLead[] = ['quiz', 'section', 'judgment', 'on_this_day', 'news', 'fraternity'];
    const lead = this.brief()?.lead;
    const ordered: BriefLead[] = lead ? [lead, ...all.filter((k) => k !== lead)] : all;
    return [ordered[0], 'court', ...ordered.slice(1)];
  });

  protected readonly today = new Date().toISOString().slice(0, 10);
  protected readonly isToday = computed(() => this.brief()?.day === this.today);

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((q) => void this.load(q.get('day'), q.get('from')));
  }

  private async load(day: string | null, from: string | null): Promise<void> {
    this.loading.set(true);
    try {
      this.brief.set(await firstValueFrom(this.briefs.get(day, from)));
    } catch {
      this.notify.error('The daily brief could not be loaded. Please try again.');
    } finally {
      this.loading.set(false);
    }
  }

  /** Day navigation: ±1 day, never past today. */
  protected shift(days: number): void {
    const b = this.brief();
    if (!b) return;
    const d = new Date(b.day + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + days);
    const next = d.toISOString().slice(0, 10);
    if (next > this.today) return;
    void this.router.navigate([], { queryParams: { day: next === this.today ? null : next }, queryParamsHandling: 'merge' });
  }

  protected async answer(index: number): Promise<void> {
    const b = this.brief();
    if (!b?.quiz || b.quiz.chosen !== null || this.answering()) return;
    this.answering.set(true);
    try {
      const r = await firstValueFrom(this.briefs.answer(b.quiz.id, index));
      this.brief.set({ ...b, quiz: { ...b.quiz, chosen: r.chosen, answer: r.answer, explanation: r.explanation, stats: r.stats } });
    } catch {
      this.notify.error('Your answer could not be saved. Please try again.');
    } finally {
      this.answering.set(false);
    }
  }

  protected optionState(i: number): 'right' | 'wrong' | 'idle' {
    const q = this.brief()?.quiz;
    if (!q || q.answer === null) return 'idle';
    if (i === q.answer) return 'right';
    return i === q.chosen ? 'wrong' : 'idle';
  }

  protected pctRight(): number {
    const s = this.brief()?.quiz?.stats;
    return s && s.answers ? Math.round((100 * s.right) / s.answers) : 0;
  }

  protected async connect(p: DirectoryPerson): Promise<void> {
    if (this.connecting().has(p.user_id)) return;
    this.connecting.update((s) => new Set(s).add(p.user_id));
    try {
      await firstValueFrom(this.network.connect(p.user_id));
      p.connection_status = 'pending_out';
      this.notify.success(`Request sent to ${p.display_name}.`);
    } catch {
      this.notify.error('The request could not be sent. Please try again.');
    }
  }

  protected sectionLink(c: DailyCard): { act: string; section: string } {
    const [act, section] = c.ref.split(':');
    return { act, section };
  }

  protected shareLink(text: string, path: string): string {
    return `https://wa.me/?text=${encodeURIComponent(`${text} — free on VidhiSangh: ${this.origin}${path}`)}`;
  }

  protected initials(name: string): string {
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase();
  }

  protected link(path: string | null): string | null {
    return path ? `${this.origin}${path}` : null;
  }
}

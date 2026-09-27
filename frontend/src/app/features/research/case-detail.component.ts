import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { ResearchService } from '@core/services/research.service';
import { CaseRead } from '@core/models/research.models';
import { DatePipe } from '@angular/common';

/**
 * One case (CNR) as a timeline of its orders — the library lists orders, and a
 * case has many. Parties, counsel and judges are the union across orders.
 */
@Component({
  selector: 'app-case-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, MatIconModule],
  templateUrl: './case-detail.component.html',
})
export class CaseDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly research = inject(ResearchService);

  protected readonly kase = signal<CaseRead | null>(null);
  protected readonly loading = signal(true);
  protected readonly notFound = signal(false);

  /** "MAC.APP. 263/2023" from the parsed registry number. */
  protected readonly caseNumber = computed(() => {
    const c = this.kase();
    if (!c?.case_type) return null;
    return `${c.case_type} ${c.case_number ?? ''}${c.case_year ? '/' + c.case_year : ''}`.trim();
  });

  /** Days between filing and the latest order — how long the case has run. */
  protected readonly runningDays = computed(() => {
    const c = this.kase();
    if (!c?.filed_on || !c.latest_order_on) return null;
    const ms = new Date(c.latest_order_on).getTime() - new Date(c.filed_on).getTime();
    return ms > 0 ? Math.round(ms / 86_400_000) : null;
  });

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => {
      const cnr = p.get('cnr');
      if (cnr) void this.load(cnr);
    });
  }

  private async load(cnr: string): Promise<void> {
    this.loading.set(true);
    this.notFound.set(false);
    try {
      this.kase.set(await firstValueFrom(this.research.case(cnr)));
    } catch {
      this.kase.set(null);
      this.notFound.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  /** "2 years 3 months" style, for the running-time line. */
  protected duration(days: number): string {
    const years = Math.floor(days / 365);
    const months = Math.floor((days % 365) / 30);
    if (years && months) return `${years} yr ${months} mo`;
    if (years) return `${years} yr`;
    if (months) return `${months} mo`;
    return `${days} days`;
  }
}

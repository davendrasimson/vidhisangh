import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { AnalyticsService } from '@core/services/analytics.service';
import { AnalyticsOverview, Bucket } from '@core/models/analytics.models';
import { MatterFieldReport } from '@core/models/matters.models';

interface StatCard {
  label: string;
  value: string;
  icon: string;
  tone: 'primary' | 'positive' | 'warn' | 'muted';
}

interface TrendColumn {
  month: string;
  invoiced: number;
  collected: number;
  invoicedPct: number;
  collectedPct: number;
}

@Component({
  selector: 'app-analytics',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  templateUrl: './analytics.component.html',
})
export class AnalyticsComponent implements OnInit {
  private readonly analytics = inject(AnalyticsService);

  protected readonly data = signal<AnalyticsOverview | null>(null);
  protected readonly loading = signal(true);
  protected readonly matterFields = signal<MatterFieldReport[]>([]);

  protected readonly revenueCards = computed<StatCard[]>(() => {
    const r = this.data()?.revenue;
    if (!r) return [];
    return [
      { label: 'Invoiced', value: this.money(r.total_invoiced), icon: 'receipt_long', tone: 'primary' },
      { label: 'Collected', value: this.money(r.total_collected), icon: 'payments', tone: 'positive' },
      { label: 'Outstanding', value: this.money(r.outstanding), icon: 'hourglass_top', tone: 'muted' },
      { label: 'Overdue', value: this.money(r.overdue_amount), icon: 'warning', tone: 'warn' },
    ];
  });

  protected readonly trend = computed<TrendColumn[]>(() => {
    const points = this.data()?.revenue_trend ?? [];
    const max = Math.max(1, ...points.flatMap((p) => [p.invoiced, p.collected]));
    return points.map((p) => ({
      month: this.monthLabel(p.month),
      invoiced: p.invoiced,
      collected: p.collected,
      invoicedPct: Math.round((p.invoiced / max) * 100),
      collectedPct: Math.round((p.collected / max) * 100),
    }));
  });

  async ngOnInit(): Promise<void> {
    try {
      const [overview, fields] = await Promise.all([
        firstValueFrom(this.analytics.overview()),
        firstValueFrom(this.analytics.matterFields()),
      ]);
      this.data.set(overview);
      this.matterFields.set(fields);
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected money(v: number): string {
    return `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  }

  protected label(key: string): string {
    return key.replace(/_/g, ' ');
  }

  protected percent(v: number): string {
    return `${Math.round(v * 100)}%`;
  }

  /** Percentage width of a bucket relative to the largest bucket in the set. */
  protected barPct(bucket: Bucket, all: Bucket[]): number {
    const max = Math.max(1, ...all.map((b) => b.count));
    return Math.round((bucket.count / max) * 100);
  }

  private monthLabel(key: string): string {
    const [year, month] = key.split('-').map(Number);
    return new Date(year, month - 1, 1).toLocaleDateString('en-IN', { month: 'short' });
  }
}

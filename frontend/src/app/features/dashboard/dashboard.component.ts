import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { TellAFriendService } from '@core/services/tell-a-friend.service';
import { UpperCasePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '@core/auth/auth.service';
import { TenantService } from '@core/services/tenant.service';
import { AnalyticsService } from '@core/services/analytics.service';
import { AnalyticsOverview } from '@core/models/analytics.models';

interface StatTile {
  label: string;
  value: string;
  icon: string;
  hint: string;
  tone: 'brand' | 'violet' | 'emerald' | 'amber';
  route: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, UpperCasePipe, RouterLink],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly auth = inject(AuthService);
  protected readonly tellAFriend = inject(TellAFriendService);
  private readonly analytics = inject(AnalyticsService);
  protected readonly tenant = inject(TenantService);

  protected readonly user = this.auth.user;
  protected readonly greeting = signal(this.timeGreeting());
  protected readonly overview = signal<AnalyticsOverview | null>(null);

  protected readonly initials = computed(() => {
    const n = this.user()?.full_name ?? '';
    return n.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || 'U';
  });

  protected readonly stats = computed<StatTile[]>(() => {
    const o = this.overview();
    const dash = (v: number | undefined) => (o ? String(v ?? 0) : '—');
    return [
      { label: 'Active matters', value: dash(o?.matters.open), icon: 'folder_shared',
        hint: o ? `${o.matters.total} total` : 'Loading…', tone: 'brand', route: '/app/matters' },
      { label: 'Upcoming hearings', value: dash(o?.productivity.upcoming_hearings), icon: 'gavel',
        hint: o ? `${o.productivity.hearings_next_7d} in next 7 days` : 'Loading…', tone: 'violet', route: '/app/calendar' },
      { label: 'Open tasks', value: dash(o?.productivity.open_tasks), icon: 'task_alt',
        hint: o ? `${o.productivity.overdue_tasks} overdue` : 'Loading…', tone: 'amber', route: '/app/matters' },
      { label: 'Outstanding', value: o ? this.inr(o.revenue.outstanding) : '—', icon: 'account_balance_wallet',
        hint: o ? `${this.inr(o.revenue.overdue_amount)} overdue` : 'Loading…', tone: 'emerald', route: '/app/billing' },
    ];
  });

  /** Conversion + revenue quick facts for the insight strip. */
  protected readonly insights = computed(() => {
    const o = this.overview();
    if (!o) return null;
    return {
      collected: this.inr(o.revenue.total_collected),
      invoiced: this.inr(o.revenue.total_invoiced),
      collectRate: o.revenue.total_invoiced > 0
        ? Math.round((o.revenue.total_collected / o.revenue.total_invoiced) * 100) : 0,
      leads: o.pipeline.total_leads,
      conversion: Math.round(o.pipeline.conversion_rate * 100),
      wonValue: this.inr(o.pipeline.won_value),
    };
  });

  /** Revenue trend chart geometry (invoiced area + collected line). */
  protected readonly chart = computed(() => {
    const o = this.overview();
    const pts = o?.revenue_trend ?? [];
    if (pts.length < 2) return null;
    const W = 720, H = 200, padL = 8, padR = 8, padT = 14, padB = 26;
    const innerW = W - padL - padR, innerH = H - padT - padB, baseY = H - padB;
    const maxY = Math.max(1, ...pts.map((p) => Math.max(p.invoiced, p.collected))) * 1.15;
    const x = (i: number) => padL + (innerW * i) / (pts.length - 1);
    const y = (v: number) => baseY - (innerH * v) / maxY;
    const line = (key: 'invoiced' | 'collected') =>
      pts.map((p, i) => `${i ? 'L' : 'M'} ${x(i).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(' ');
    const invLine = line('invoiced');
    const area = `${invLine} L ${x(pts.length - 1).toFixed(1)} ${baseY} L ${x(0).toFixed(1)} ${baseY} Z`;
    return {
      W, H, baseY, area, invLine, colLine: line('collected'),
      dots: pts.map((p, i) => ({ cx: x(i), cyc: y(p.collected), cyi: y(p.invoiced) })),
      labels: pts.map((p, i) => ({ x: x(i), text: this.monthLabel(p.month) })),
      grid: [0.25, 0.5, 0.75, 1].map((f) => baseY - innerH * f),
    };
  });

  protected readonly modules = [
    { name: 'Legal Research', icon: 'gavel', desc: 'Judgments, citations & search.', route: '/app/research' },
    { name: 'Matters', icon: 'folder_shared', desc: 'Cases, hearings, tasks & timelines.', route: '/app/matters' },
    { name: 'Documents', icon: 'description', desc: 'Folders, versions & full-text search.', route: '/app/documents' },
    { name: 'Billing & CRM', icon: 'payments', desc: 'Invoices, GST, leads & pipeline.', route: '/app/billing' },
    { name: 'Network', icon: 'groups', desc: 'Feed, connections & messaging.', route: '/app/network' },
    { name: 'Knowledge', icon: 'menu_book', desc: 'Templates, precedents & SOPs.', route: '/app/knowledge' },
  ];

  async ngOnInit(): Promise<void> {
    try {
      await firstValueFrom(this.tenant.load());
    } catch {
      /* handled */
    }
    try {
      this.overview.set(await firstValueFrom(this.analytics.overview()));
    } catch {
      /* handled */
    }
  }

  protected inr(n: number): string {
    if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
    if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
    if (n >= 1e3) return `₹${(n / 1e3).toFixed(0)}K`;
    return `₹${Math.round(n)}`;
  }

  private monthLabel(m: string): string {
    const d = new Date(m + '-01');
    return d.toLocaleDateString('en-IN', { month: 'short' });
  }

  private timeGreeting(): string {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  }
}

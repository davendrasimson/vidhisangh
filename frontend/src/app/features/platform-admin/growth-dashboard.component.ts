import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { SupportService } from '@core/services/support.service';
import { GrowthPoint, GrowthSlice, RegistrationGrowth } from '@core/models/support.models';

type Period = 'daily' | 'weekly' | 'monthly';

const W = 720, H = 260, LEFT = 34, RIGHT = 44, TOP = 22, BOTTOM = 34;

const FUNNEL_LABELS: Record<string, string> = {
  landing_view: 'Home page seen', register_view: 'Sign-up page opened', email_form_opened: 'Email form opened',
  whatsapp_code_requested: 'WhatsApp code asked', account_created: 'Account created',
};

/**
 * Platform admin → Growth. Registrations by day / week / month (India time).
 * Built for small numbers: absolute changes ("+2 vs yesterday"), a percentage
 * only once the comparison base is 5 or more, value labels on every bar, the
 * running total as a line, and the next membership milestone.
 */
@Component({
  selector: 'app-growth-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, DecimalPipe, MatButtonModule, MatIconModule],
  template: `
    <header class="flex flex-wrap items-end gap-3">
      <div class="flex-1 min-w-0">
        <h1 class="text-2xl font-bold">Registrations &amp; growth</h1>
        <p class="text-content-muted">New members by day, week and month, India time.
          @if (data(); as d) { Updated {{ d.generated_at | date:'dd/MM/yyyy, h:mm a' }}. }</p>
      </div>
      <button mat-stroked-button (click)="load()" [disabled]="loading()"><mat-icon class="material-icons-outlined">refresh</mat-icon> Refresh</button>
    </header>

    @if (error()) { <p class="mt-6 text-danger">{{ error() }}</p> }
    @if (data(); as d) {
      <!-- Milestone -->
      <section class="rounded-card border border-line bg-surface-raised p-5 mt-6">
        <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <strong class="text-4xl">{{ d.total_members | number }}</strong>
          <span class="text-content-muted">members</span>
          <span class="flex-1"></span>
          @if (d.next_milestone) {
            <span class="text-sm"><strong>{{ d.next_milestone - d.total_members }}</strong> to go for <strong>{{ d.next_milestone | number }}</strong></span>
          }
        </div>
        @if (d.next_milestone) {
          <div class="h-3 rounded-full bg-surface-sunken mt-3 overflow-hidden" role="progressbar"
               [attr.aria-valuenow]="d.total_members" [attr.aria-valuemax]="d.next_milestone">
            <div class="h-full rounded-full bg-brand transition-all" [style.width.%]="milestonePct()"></div>
          </div>
        }
        <p class="text-xs text-content-muted mt-2">
          {{ d.self_signups }} signed up themselves · {{ d.added_by_firms }} added by firms · {{ d.via_invite }} through invite links
          @if (d.days_since_last !== null) {
            · last sign-up {{ d.days_since_last === 0 ? 'today' : d.days_since_last === 1 ? 'yesterday' : d.days_since_last + ' days ago' }}
          }
        </p>
      </section>

      <!-- KPIs -->
      <div class="grid grid-cols-2 xl:grid-cols-4 gap-3 mt-4">
        @for (k of kpis(); track k.label) {
          <div class="rounded-card bg-surface-raised border border-line p-4">
            <small class="text-content-muted">{{ k.label }}</small>
            <strong class="block text-3xl mt-1">{{ k.value }}</strong>
            <span class="text-xs" [class.text-success]="k.diff > 0" [class.text-danger]="k.diff < 0" [class.text-content-muted]="k.diff === 0">{{ k.note }}</span>
          </div>
        }
      </div>

      <!-- Chart -->
      <section class="rounded-card border border-line bg-surface-raised p-5 mt-4">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-semibold flex-1">New members per {{ unit() }}</h2>
          <div class="inline-flex rounded-full border border-line p-0.5" role="tablist" aria-label="Period">
            @for (p of periods; track p.id) {
              <button type="button" role="tab" class="px-3 py-1 rounded-full text-sm"
                      [class.bg-brand]="period() === p.id" [class.text-white]="period() === p.id"
                      [attr.aria-selected]="period() === p.id" (click)="period.set(p.id)">{{ p.label }}</button>
            }
          </div>
        </div>
        <p class="text-sm text-content-muted mt-1">
          {{ periodTotal() }} in the {{ periodSpan() }} ·
          <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-sm bg-brand"></span>new</span> ·
          <span class="inline-flex items-center gap-1"><span class="inline-block w-4 border-t-2 border-warning"></span>total members</span>
        </p>
        <div class="overflow-x-auto mt-3 -mx-1 px-1">
        <svg [attr.viewBox]="'0 0 ' + W + ' ' + H" class="w-full min-w-[600px] h-auto" role="img"
             [attr.aria-label]="'New members per ' + unit() + ' and running total'">
          @for (t of chart().ticks; track t.value) {
            <line [attr.x1]="LEFT" [attr.x2]="W - RIGHT" [attr.y1]="t.y" [attr.y2]="t.y" class="text-line" stroke="currentColor" stroke-dasharray="3 4" />
            <text [attr.x]="LEFT - 8" [attr.y]="t.y + 4" text-anchor="end" class="fill-current text-content-muted" font-size="11">{{ t.value }}</text>
          }
          @for (b of chart().bars; track b.start) {
            <g>
              <title>{{ b.label }}: {{ b.count }} new, {{ b.cumulative }} total</title>
              <rect [attr.x]="b.x" [attr.y]="b.y" [attr.width]="b.w" [attr.height]="b.h" rx="3" class="text-brand" fill="currentColor" />
              @if (b.count > 0) {
                <text [attr.x]="b.cx" [attr.y]="b.y - 5" text-anchor="middle" font-size="11" font-weight="700" class="fill-current text-content">{{ b.count }}</text>
              }
              @if (b.showLabel) {
                <text [attr.x]="b.cx" [attr.y]="H - 12" text-anchor="middle" font-size="11" class="fill-current text-content-muted">{{ b.label }}</text>
              }
            </g>
          }
          <polyline [attr.points]="chart().line" fill="none" class="text-warning" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round" />
          @for (b of chart().bars; track b.start) {
            <circle [attr.cx]="b.cx" [attr.cy]="b.ly" r="3" class="text-warning" fill="currentColor"><title>{{ b.label }}: {{ b.cumulative }} total</title></circle>
          }
          <text [attr.x]="W - RIGHT + 6" [attr.y]="chart().lastLy + 4" font-size="11" font-weight="700" class="fill-current text-warning">{{ chart().lastTotal }}</text>
        </svg>
        </div>
      </section>

      <!-- Breakdowns -->
      <div class="grid lg:grid-cols-3 gap-4 mt-4">
        <section class="rounded-card border border-line bg-surface-raised p-5">
          <h2 class="font-semibold">How they joined</h2>
          @for (s of d.by_method; track s.key) {
            <div class="mt-3"><div class="flex text-sm"><span class="flex-1">{{ s.label }}</span><strong>{{ s.count }}</strong><span class="w-12 text-right text-content-muted">{{ pct(s, d.total_members) }}%</span></div>
              <div class="h-2 rounded-full bg-surface-sunken mt-1"><div class="h-full rounded-full bg-brand" [style.width.%]="pct(s, d.total_members)"></div></div></div>
          } @empty { <p class="text-sm text-content-muted mt-3">No members yet.</p> }
        </section>
        <section class="rounded-card border border-line bg-surface-raised p-5">
          <h2 class="font-semibold">Who they are</h2>
          @for (s of d.by_role; track s.key) {
            <div class="mt-3"><div class="flex text-sm"><span class="flex-1">{{ s.label }}</span><strong>{{ s.count }}</strong><span class="w-12 text-right text-content-muted">{{ pct(s, d.total_members) }}%</span></div>
              <div class="h-2 rounded-full bg-surface-sunken mt-1"><div class="h-full rounded-full bg-success" [style.width.%]="pct(s, d.total_members)"></div></div></div>
          } @empty { <p class="text-sm text-content-muted mt-3">No members yet.</p> }
        </section>
        <section class="rounded-card border border-line bg-surface-raised p-5">
          <h2 class="font-semibold">Quality</h2>
          <dl class="grid grid-cols-2 gap-4 mt-3 text-sm">
            <div><dt class="text-content-muted">Verified</dt><dd class="text-2xl font-bold">{{ ratio(d.verified, d.total_members) }}%</dd><dd class="text-xs text-content-muted">{{ d.verified }} of {{ d.total_members }}</dd></div>
            <div><dt class="text-content-muted">Came back</dt><dd class="text-2xl font-bold">{{ ratio(d.returned, d.total_members) }}%</dd><dd class="text-xs text-content-muted">signed in on a later day</dd></div>
            <div><dt class="text-content-muted">Via invites</dt><dd class="text-2xl font-bold">{{ d.via_invite }}</dd></div>
            <div><dt class="text-content-muted">Best day</dt>
              @if (d.best_day; as best) { <dd class="text-2xl font-bold">{{ best.count }}</dd><dd class="text-xs text-content-muted">{{ best.date | date:'dd/MM/yyyy' }}</dd> }
              @else { <dd>—</dd> }</div>
          </dl>
        </section>
      </div>

      <!-- Funnel -->
      @if (d.funnel; as f) {
        <section class="rounded-card border border-line bg-surface-raised p-5 mt-4">
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="font-semibold flex-1">Sign-up funnel</h2>
            <div class="flex gap-1" role="group" aria-label="Funnel period">
              <button mat-stroked-button [class.!bg-brand]="funnelDays() === 7" [class.!text-white]="funnelDays() === 7" (click)="funnelDays.set(7)">7 days</button>
              <button mat-stroked-button [class.!bg-brand]="funnelDays() === 30" [class.!text-white]="funnelDays() === 30" (click)="funnelDays.set(30)">30 days</button>
            </div>
          </div>
          <p class="text-xs text-content-muted mt-1">Anonymous daily counts on our own server (no cookies or trackers), once per visitor tab.@if (f.since) { Counting since {{ f.since | date:'dd/MM/yyyy' }}. }</p>
          <ol class="grid gap-2 mt-3">
            @for (s of funnelSteps(); track s.step; let i = $index) {
              <li class="grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto] items-center gap-3 text-sm">
                <span>{{ s.label }}</span>
                <span class="h-3 rounded-full bg-line overflow-hidden"><span class="block h-full bg-brand" [style.width.%]="s.width"></span></span>
                <span class="whitespace-nowrap"><strong>{{ s.count | number }}</strong>@if (s.rate !== null) { <small class="text-content-muted"> · {{ s.rate }}% of previous</small> }</span>
              </li>
            }
          </ol>
        </section>
      }

      <!-- Recent -->
      <section class="rounded-card border border-line bg-surface-raised p-5 mt-4">
        <h2 class="font-semibold">Latest sign-ups</h2>
        <div class="overflow-x-auto mt-3">
          <table class="w-full text-sm">
            <thead class="text-left text-content-muted"><tr><th class="py-2 pr-3">Name</th><th class="pr-3">Role</th><th class="pr-3">Joined via</th><th class="pr-3">When</th><th>Verified</th></tr></thead>
            <tbody>
              @for (r of d.recent; track r.joined_at + r.name) {
                <tr class="border-t border-line">
                  <td class="py-2 pr-3 font-medium">{{ r.name }} @if (r.invited) { <span class="vs-chip ml-1">invited</span> }</td>
                  <td class="pr-3">{{ r.role }}</td><td class="pr-3">{{ r.method }}</td>
                  <td class="pr-3 whitespace-nowrap">{{ r.joined_at | date:'dd/MM/yyyy, h:mm a' }}</td>
                  <td>@if (r.verified) { <mat-icon class="material-icons-outlined text-success align-middle">check_circle</mat-icon> } @else { <span class="text-content-muted">pending</span> }</td>
                </tr>
              } @empty { <tr><td colspan="5" class="py-3 text-content-muted">No members yet.</td></tr> }
            </tbody>
          </table>
        </div>
      </section>
    } @else if (loading()) { <p class="mt-6 text-content-muted">Loading registrations…</p> }
  `,
})
export class GrowthDashboardComponent implements OnInit {
  protected readonly funnelDays = signal<7 | 30>(7);
  /** Steps with a bar scaled to the first step and the share that reached each from the one before. */
  protected readonly funnelSteps = computed(() => {
    const f = this.data()?.funnel;
    const rows = f ? (this.funnelDays() === 7 ? f.last_7_days : f.last_30_days) : [];
    const top = Math.max(1, ...rows.map((r) => r.count));
    return rows.map((r, i) => ({
      ...r, label: FUNNEL_LABELS[r.step] ?? r.step, width: (r.count / top) * 100,
      rate: i > 0 && rows[i - 1].count >= 5 ? Math.round((r.count / rows[i - 1].count) * 100) : null,
    }));
  });
  private readonly support = inject(SupportService);
  protected readonly W = W; protected readonly H = H; protected readonly LEFT = LEFT; protected readonly RIGHT = RIGHT;
  protected readonly data = signal<RegistrationGrowth | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly period = signal<Period>('daily');
  protected readonly periods: { id: Period; label: string }[] = [
    { id: 'daily', label: 'Daily' }, { id: 'weekly', label: 'Weekly' }, { id: 'monthly', label: 'Monthly' },
  ];

  async ngOnInit(): Promise<void> { await this.load(); }

  async load(): Promise<void> {
    this.loading.set(true); this.error.set(null);
    try { this.data.set(await firstValueFrom(this.support.growth())); }
    catch { this.error.set('Could not load registration figures.'); }
    finally { this.loading.set(false); }
  }

  protected readonly unit = computed(() => ({ daily: 'day', weekly: 'week', monthly: 'month' })[this.period()]);
  protected readonly periodSpan = computed(() => ({ daily: 'last 30 days', weekly: 'last 12 weeks', monthly: 'last 12 months' })[this.period()]);
  private readonly points = computed<GrowthPoint[]>(() => this.data()?.[this.period()] ?? []);
  protected readonly periodTotal = computed(() => this.points().reduce((n, p) => n + p.count, 0));

  protected readonly milestonePct = computed(() => {
    const d = this.data();
    if (!d?.next_milestone) return 100;
    const span = d.next_milestone - d.previous_milestone;
    return Math.max(2, Math.round(((d.total_members - d.previous_milestone) / span) * 100));
  });

  protected readonly kpis = computed(() => {
    const k = this.data()?.kpis;
    if (!k) return [];
    return [
      { label: 'Today so far', ...delta(k.today, k.yesterday, 'yesterday') },
      { label: 'This week', ...delta(k.this_week, k.last_week_same_point, 'this point last week') },
      { label: 'This month', ...delta(k.this_month, k.last_month, 'all of last month') },
      { label: 'Last 30 days', ...delta(k.last_30_days, k.previous_30_days, 'previous 30 days') },
    ];
  });

  protected readonly chart = computed(() => {
    const pts = this.points();
    const n = Math.max(pts.length, 1);
    const plotW = W - LEFT - RIGHT, plotH = H - TOP - BOTTOM;
    const maxCount = Math.max(1, ...pts.map(p => p.count));
    const step = niceStep(maxCount);
    const top = Math.ceil(maxCount / step) * step;
    const maxCum = Math.max(1, ...pts.map(p => p.cumulative));
    const slot = plotW / n, bw = Math.max(4, Math.min(36, slot * 0.62));
    const every = Math.ceil(n / 8);
    const bars = pts.map((p, i) => {
      const h = (p.count / top) * plotH;
      const cx = LEFT + slot * i + slot / 2;
      return { ...p, x: cx - bw / 2, w: bw, h, y: TOP + plotH - h, cx,
        ly: TOP + plotH - (p.cumulative / maxCum) * plotH * 0.92,
        showLabel: (n - 1 - i) % every === 0 };
    });
    const ticks = [];
    for (let v = 0; v <= top; v += step) ticks.push({ value: v, y: TOP + plotH - (v / top) * plotH });
    const last = bars[bars.length - 1];
    return { bars, ticks, line: bars.map(b => `${b.cx},${b.ly}`).join(' '),
      lastLy: last?.ly ?? TOP + plotH, lastTotal: last?.cumulative ?? 0 };
  });

  protected pct(s: GrowthSlice, total: number): number { return this.ratio(s.count, total); }
  protected ratio(part: number, total: number): number { return total ? Math.round((part / total) * 100) : 0; }
}

/** "+2 vs yesterday"; a percentage only when the base is big enough to mean something. */
function delta(value: number, previous: number, against: string): { value: number; diff: number; note: string } {
  const diff = value - previous;
  if (diff === 0) return { value, diff, note: `same as ${against}` };
  const pct = previous >= 5 ? ` (${diff > 0 ? '+' : ''}${Math.round((diff / previous) * 100)}%)` : '';
  return { value, diff, note: `${diff > 0 ? '+' : '−'}${Math.abs(diff)} vs ${against}${pct}` };
}

function niceStep(max: number): number {
  if (max <= 5) return 1;
  const raw = max / 5, mag = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map(m => m * mag).find(s => s >= raw) ?? raw;
}

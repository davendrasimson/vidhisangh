import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '@core/auth/auth.service';
import { TenantService } from '@core/services/tenant.service';
import { AnalyticsService } from '@core/services/analytics.service';
import { CalendarService } from '@core/services/calendar.service';
import { MattersService } from '@core/services/matters.service';
import { NetworkService } from '@core/services/network.service';
import { MessagingService } from '@core/services/messaging.service';
import { ProfileService } from '@core/services/profile.service';
import { GroupsService } from '@core/services/groups.service';
import { GroupFeedItem } from '@core/models/groups.models';
import { TellAFriendService, whatsappInvite } from '@core/services/tell-a-friend.service';
import { NotificationService } from '@core/services/notification.service';
import { AnalyticsOverview } from '@core/models/analytics.models';
import { AgendaItem } from '@core/models/calendar.models';
import { Connection, DailyCard, DailyRead, DirectoryPerson, HomeNetwork } from '@core/models/network.models';
import { Conversation } from '@core/models/messaging.models';
import { profilePercent, profileSteps } from '@core/home/profile-progress';
import { publicOrigin } from '@core/platform/platform';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';
import { WhatsappUpdatesComponent } from '@shared/whatsapp-updates/whatsapp-updates.component';

interface StatTile {
  label: string;
  value: string;
  icon: string;
  hint: string;
  tone: 'brand' | 'violet' | 'emerald' | 'amber';
  route: string;
}

type SearchWhere = 'judgments' | 'acts';

/** Free tools and converters: static pages on vidhisangh.com (open in the browser). */
export const QUICK_TOOLS = [
  { label: 'IPC → BNS', path: '/acts/ipc-to-bns/' },
  { label: 'CrPC → BNSS', path: '/acts/crpc-to-bnss/' },
  { label: 'Evidence → BSA', path: '/acts/evidence-to-bsa/' },
  { label: 'Limitation calculator', path: '/tools/limitation-calculator/' },
  { label: 'Default bail', path: '/tools/default-bail-calculator/' },
  { label: 'Interest calculator', path: '/tools/interest-calculator/' },
];

/**
 * Home: a daily screen for an advocate or law student (22 Oct 2026). Top to
 * bottom: today's and tomorrow's hearings and deadlines, acted on in place
 * (held / adjourned → next date, tick a task); one search box for judgments
 * and Bare Acts with the free tools; the section, judgment and news of the
 * day. Firm figures (stats, revenue, action centre) only appear once there
 * is something in them, so a new member never faces a wall of zeros.
 *
 * A sitting judicial officer (`judge`) gets the same screen in the court's
 * words: today's board of cases heard or adjourned, no clients, no fees. Their
 * token has no practice-analytics code, so the firm figures never load.
 */
@Component({
  selector: 'app-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, MatButtonModule, DatePipe, DecimalPipe, RouterLink, FormsModule, VsDateInputComponent, WhatsappUpdatesComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly analytics = inject(AnalyticsService);
  private readonly calendar = inject(CalendarService);
  private readonly matters = inject(MattersService);
  private readonly network = inject(NetworkService);
  private readonly notify = inject(NotificationService);
  private readonly messaging = inject(MessagingService);
  private readonly profile = inject(ProfileService);
  private readonly groups = inject(GroupsService);
  private readonly invites = inject(TellAFriendService);
  protected readonly tenant = inject(TenantService);
  protected readonly today = new Date();
  protected readonly tools = QUICK_TOOLS;
  protected readonly origin = publicOrigin();

  protected readonly user = this.auth.user;
  protected readonly judge = this.auth.isJudicial;
  protected readonly greeting = signal(this.timeGreeting());
  protected readonly firstName = computed(() => {
    const parts = (this.user()?.full_name ?? '').replace(/^(adv\.?|advocate|hon'?ble|justice|dr\.?|mr\.?|ms\.?|mrs\.?)\s+/i, '').split(/\s+/);
    return parts[0] || '';
  });
  protected readonly overview = signal<AnalyticsOverview | null>(null);
  protected readonly daily = signal<DailyRead | null>(null);

  // ── Today's board ─────────────────────────────────────────────────
  protected readonly agenda = signal<AgendaItem[] | null>(null);
  protected readonly board = computed(() => {
    const items = (this.agenda() ?? []).filter((i) => i.kind === 'hearing' || i.kind === 'deadline');
    const endOfToday = this.dayStart(1).getTime();
    return {
      today: items.filter((i) => new Date(i.start_at).getTime() < endOfToday),
      tomorrow: items.filter((i) => new Date(i.start_at).getTime() >= endOfToday),
    };
  });
  /** Hearing just marked held/adjourned: ask for the next date right here. */
  protected readonly nextFor = signal<AgendaItem | null>(null);
  protected nextDate = '';
  protected readonly busy = signal<string | null>(null);

  // ── People first: colleagues in my city, newest members, fraternity numbers ──
  protected readonly homeNet = signal<HomeNetwork | null>(null);
  /** Up to five people to connect with: same city first, then the newest members. */
  protected readonly suggestions = computed<DirectoryPerson[]>(() => {
    const h = this.homeNet();
    return h ? [...h.nearby, ...h.recent].slice(0, 5) : [];
  });
  protected readonly asked = signal<Set<string>>(new Set());

  // ── Network: requests to answer, messages to read ─────────────────
  protected readonly requests = signal<Connection[]>([]);
  protected readonly unread = signal<Conversation[]>([]);
  protected readonly unreadTotal = computed(() => this.unread().reduce((n, c) => n + c.unread_count, 0));
  /** The newest posts across the member's groups (hidden until they join one that has posts). */
  protected readonly groupPosts = signal<GroupFeedItem[]>([]);

  // ── Progress: profile completeness and the invite goal ────────────
  protected readonly steps = signal<ReturnType<typeof profileSteps> | null>(null);
  protected readonly percent = computed(() => profilePercent(this.steps() ?? []));
  protected readonly nextStep = computed(() => this.steps()?.find((s) => !s.done) ?? null);
  protected readonly referral = this.invites.referral;
  protected readonly inviteGoal = computed(() => this.referral()?.founding_goal ?? 3);
  protected readonly inviteRemaining = computed(() => Math.max(0, this.inviteGoal() - (this.referral()?.joined ?? 0)));
  protected readonly inviteLink = computed(() => whatsappInvite(this.referral()?.link ?? this.origin + '/'));
  /** Shown while something is still to do: profile incomplete or badge not yet earned. */
  protected readonly showProgress = computed(() =>
    (this.steps() !== null && this.percent() < 100) || (this.referral() !== null && !this.referral()!.founding_member));

  // ── Search ────────────────────────────────────────────────────────
  protected searchWhere: SearchWhere = 'judgments';
  protected searchText = '';

  /** Firm figures only once there is something to show. */
  protected readonly hasPractice = computed(() => {
    const o = this.overview();
    return !!o && (o.matters.total > 0 || o.revenue.total_invoiced > 0 || o.pipeline.total_leads > 0);
  });
  protected readonly hasOperations = computed(() => {
    const op = this.overview()?.operations;
    return !!op && (op.submitted_time_entries + op.pending_signatures + op.follow_ups_due > 0 || op.unbilled_time_value > 0);
  });
  protected readonly hasRevenue = computed(() => (this.overview()?.revenue.total_invoiced ?? 0) > 0);
  /** No matters at all yet: the board invites the first case instead. */
  protected readonly noMatters = computed(() => this.overview()?.matters.total === 0);

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

  async ngOnInit(): Promise<void> {
    // Independent: one failing (e.g. no calendar permission) never blanks the rest.
    void firstValueFrom(this.tenant.load()).catch(() => undefined);
    void this.loadAgenda();
    void firstValueFrom(this.network.daily()).then((d) => this.daily.set(d)).catch(() => undefined);
    if (this.auth.hasPermission('analytics:view')) {
      void firstValueFrom(this.analytics.overview()).then((o) => this.overview.set(o)).catch(() => undefined);
    }
    void firstValueFrom(this.network.home()).then((h) => this.homeNet.set(h)).catch(() => undefined);
    void firstValueFrom(this.network.incomingRequests()).then((r) => this.requests.set(r)).catch(() => undefined);
    void firstValueFrom(this.messaging.list()).then((c) => this.unread.set(c.filter((x) => x.unread_count > 0))).catch(() => undefined);
    void firstValueFrom(this.profile.myProfile()).then((p) => this.steps.set(profileSteps(p))).catch(() => undefined);
    if (this.auth.hasPermission('group:read')) {
      void firstValueFrom(this.groups.latestInMyGroups(3)).then((p) => this.groupPosts.set(p)).catch(() => undefined);
    }
    void this.invites.loadReferral();
  }

  protected async answerRequest(c: Connection, accept: boolean): Promise<void> {
    if (this.busy()) return;
    this.busy.set(c.id);
    try {
      await firstValueFrom(accept ? this.network.acceptConnection(c.id) : this.network.declineConnection(c.id));
      this.requests.update((list) => list.filter((x) => x.id !== c.id));
      if (accept) this.notify.success(`You and ${c.requester?.display_name ?? 'they'} are now connected.`);
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  /** Ask a suggested colleague to connect, from the home card. */
  protected async connect(p: DirectoryPerson): Promise<void> {
    if (this.busy()) return;
    this.busy.set(p.user_id);
    try {
      await firstValueFrom(this.network.connect(p.user_id));
      this.asked.update((s) => new Set(s).add(p.user_id));
      this.notify.success(`Request sent to ${p.display_name}.`);
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  /** Appear in the People directory so colleagues can find me. */
  protected async beFound(): Promise<void> {
    if (this.busy()) return;
    this.busy.set('discoverable');
    try {
      await firstValueFrom(this.network.setDiscoverable(true));
      this.homeNet.update((h) => (h ? { ...h, discoverable: true } : h));
      this.notify.success('You are now listed. Colleagues in your city can find you.');
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  protected initials(name: string): string {
    return name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w) && !/^(adv|advocate|dr|mr|ms|mrs|smt|shri|sh)\.?$/i.test(w))
      .slice(0, 2).map((w) => w[0].toUpperCase()).join('') || name.slice(0, 1).toUpperCase();
  }

  /** The first line or so of a post, without markup. */
  protected snippet(p: GroupFeedItem): string {
    const text = p.content.replace(/\s+/g, ' ').trim();
    return text.length > 160 ? `${text.slice(0, 157).trimEnd()}…` : text;
  }

  /** "5 min ago", "3 h ago", "2 days ago" for the group card. */
  protected ago(iso: string): string {
    const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} h ago`;
    const days = Math.round(hours / 24);
    return days === 1 ? 'yesterday' : `${days} days ago`;
  }

  /** Who the conversation is with (the other participants), for the unread list. */
  protected withWhom(c: Conversation): string {
    const me = this.user()?.id;
    const others = c.participants.filter((p) => p.user_id !== me).map((p) => p.participant_name);
    return c.title || others.join(', ') || 'Conversation';
  }

  private async loadAgenda(): Promise<void> {
    try {
      const items = await firstValueFrom(this.calendar.agenda(this.dayStart(0).toISOString(), this.dayStart(2).toISOString()));
      this.agenda.set(items);
    } catch {
      this.agenda.set([]);
    }
  }

  /** Midnight `days` from today, on this device's clock. */
  private dayStart(days: number): Date {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() + days);
    return d;
  }

  protected courtLine(i: AgendaItem): string {
    return [i.court ?? i.location, i.court_room ? `Court ${i.court_room}` : '', i.item_number ? `Item ${i.item_number}` : '']
      .filter(Boolean).join(' · ');
  }

  /** Held / adjourned only once the day has come, never for tomorrow's. */
  protected canMark(i: AgendaItem): boolean {
    return i.kind === 'hearing' && i.status === 'scheduled' && new Date(i.start_at).getTime() < this.dayStart(1).getTime();
  }

  protected async markHearing(i: AgendaItem, status: 'held' | 'adjourned'): Promise<void> {
    if (this.busy()) return;
    this.busy.set(i.id);
    try {
      await firstValueFrom(this.matters.updateHearing(i.id, { status }));
      this.agenda.update((list) => (list ?? []).map((x) => (x.id === i.id ? { ...x, status } : x)));
      this.nextDate = '';
      this.nextFor.set(i);
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  /** The next date given in court: a new hearing in the same court and courtroom. */
  protected async addNextDate(): Promise<void> {
    const prev = this.nextFor();
    if (!prev?.matter_id || !this.nextDate || this.busy()) return;
    this.busy.set(prev.id);
    try {
      await firstValueFrom(this.matters.addHearing(prev.matter_id, {
        scheduled_on: this.nextDate, court: prev.court ?? null, court_room: prev.court_room ?? null,
      }));
      this.nextFor.set(null);
      this.notify.success('Next date added to your diary.');
      void this.loadAgenda();
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  protected async completeTask(i: AgendaItem): Promise<void> {
    if (this.busy()) return;
    this.busy.set(i.id);
    try {
      await firstValueFrom(this.matters.setTaskDone(i.id));
      this.agenda.update((list) => (list ?? []).filter((x) => x.id !== i.id));
      this.notify.success('Done.');
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  // ── Search ────────────────────────────────────────────────────────
  protected search(): void {
    const q = this.searchText.trim();
    if (q.length < 2) return;
    if (this.searchWhere === 'judgments') void this.router.navigate(['/app/research'], { queryParams: { q } });
    else void this.router.navigate(['/app/knowledge'], { queryParams: { view: 'acts', q } });
  }

  // ── Daily cards ───────────────────────────────────────────────────
  /** The section of the day in the in-app Bare Act reader ("bns:318"). */
  protected sectionLink(c: DailyCard): { act: string; section: string } {
    const [act, section] = c.ref.split(':');
    return { act, section };
  }

  protected shareLink(c: DailyCard): string {
    const url = c.kind === 'judgment' ? `${this.origin}/judgments/${c.ref}/` : c.url ?? this.origin;
    return `https://wa.me/?text=${encodeURIComponent(`${c.title} — free on VidhiSangh: ${url}`)}`;
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

import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { environment } from '@env/environment';
import { NotificationService } from '@core/services/notification.service';
import { problemMessage } from '@core/http/problem-message';

interface FunnelRow { sent: number; delivered: number; opened: number; clicked: number; joined: number }
interface Funnel {
  total: FunnelRow & { joined_via_email: number; bounced: number; complained: number; unsubscribed: number };
  by_day: (FunnelRow & { day: string })[];
  by_court: (FunnelRow & { court: string })[];
}
interface OutreachOverview {
  paused: boolean; daily_limit: number; max_daily_limit: number; sender_configured: boolean; webhook_configured: boolean; from_address: string;
  focus: string | null; queued_in_focus: number | null;
  sent_today: number; sent_last_7_days: number; suppressed_total: number; sending: boolean;
  counts: Record<'queued' | 'sent' | 'joined' | 'unsubscribed' | 'bounced' | 'skipped' | 'removal_requested', number>;
  funnel: Funnel;
  recent: { email: string; name: string | null; status: string; source: string; sent_at: string | null; updated_at: string }[];
}
type ImportReport = Record<'added' | 'duplicate' | 'member' | 'unsubscribed' | 'invalid' | 'no_source', number>;
type ContactStatus = 'queued' | 'sent' | 'joined' | 'unsubscribed' | 'bounced' | 'skipped' | 'removal_requested';
interface Contact {
  id: string; email: string; name: string | null; mobile: string | null; city: string | null; court: string | null; source: string;
  status: ContactStatus; sent_at: string | null; unsubscribed_at: string | null; removal_requested_at: string | null;
  removal_note: string | null; last_error: string | null; created_at: string; updated_at: string;
  delivered_at: string | null; opened_at: string | null; clicked_at: string | null; complained_at: string | null;
}
interface ContactPage { items: Contact[]; total: number; page: number; size: number }
const STATUS_LABEL: Record<ContactStatus, string> = {
  queued: 'Waiting', sent: 'Approached', joined: 'Joined', unsubscribed: 'Unsubscribed', bounced: 'Bounced',
  skipped: 'Skipped', removal_requested: 'Asked to be removed',
};

/** Platform admin → Outreach: the daily invitation emails to non-members. */
@Component({
  selector: 'app-outreach-admin',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, DecimalPipe, FormsModule, MatButtonModule, MatIconModule],
  template: `
    <header class="flex flex-wrap items-end gap-3">
      <div class="flex-1 min-w-0">
        <h1 class="text-2xl font-bold">Invitation emails</h1>
        <p class="text-content-muted">One invitation per address, at most {{ o()?.max_daily_limit ?? 50 }} a day (weekday mornings), with one-click unsubscribe.</p>
      </div>
      <button mat-stroked-button (click)="load()"><mat-icon class="material-icons-outlined">refresh</mat-icon> Refresh</button>
    </header>

    @if (o(); as d) {
      @if (!d.sender_configured) {
        <div class="mt-5 rounded-card border border-warning/50 bg-warning/10 p-4 text-sm">
          <strong>Mail service not connected yet.</strong> Contacts can be added and previewed, but nothing is sent until the
          invitation mail service (news.vidhisangh.com) is set up on the server.
        </div>
      }
      <div class="grid grid-cols-2 xl:grid-cols-4 gap-3 mt-5">
        <div class="rounded-card border border-line bg-surface-raised p-4"><small class="text-content-muted">Waiting to be sent</small><strong class="block text-3xl mt-1">{{ d.counts.queued }}</strong><span class="text-xs text-content-muted">about {{ daysLeft() }} sending day{{ daysLeft() === 1 ? '' : 's' }}</span></div>
        <div class="rounded-card border border-line bg-surface-raised p-4"><small class="text-content-muted">Sent today / last 7 days</small><strong class="block text-3xl mt-1">{{ d.sent_today }} <span class="text-lg text-content-muted">/ {{ d.sent_last_7_days }}</span></strong><span class="text-xs text-content-muted">{{ d.counts.sent }} invited in total</span></div>
        <div class="rounded-card border border-line bg-surface-raised p-4"><small class="text-content-muted">Joined</small><strong class="block text-3xl mt-1 text-success">{{ d.counts.joined }}</strong><span class="text-xs text-content-muted">{{ joinRate() }}% of those invited</span></div>
        <div class="rounded-card border border-line bg-surface-raised p-4"><small class="text-content-muted">Unsubscribed · bounced</small><strong class="block text-3xl mt-1">{{ d.counts.unsubscribed }} <span class="text-lg text-content-muted">· {{ d.counts.bounced }}</span></strong><span class="text-xs text-content-muted">{{ d.suppressed_total }} on the do-not-email list</span></div>
      </div>

      <section class="rounded-card border border-line bg-surface-raised p-5 mt-4">
        <div class="flex flex-wrap items-baseline gap-3">
          <h2 class="font-semibold flex-1">Who reads it and who joins</h2>
          <span class="text-xs text-content-muted">Opens count mail apps that fetched the image (Gmail and Apple do this for everyone, so read it as "at least"). Clicks and joins are exact.</span>
        </div>
        @if (!d.webhook_configured) {
          <p class="text-sm text-warning mt-2">Delivered, bounces and complaints come from the mail relay's webhook, which is not connected yet; until then the bounce figure here undercounts and Brevo's dashboard is the one to trust.</p>
        }
        <div class="flex flex-wrap items-stretch gap-2 mt-3">
          @for (step of funnelSteps(); track step.label) {
            <div class="flex-1 min-w-[7rem] rounded-lg border border-line p-3" [class.border-success]="step.label === 'Joined'">
              <small class="text-content-muted">{{ step.label }}</small>
              <strong class="block text-2xl" [class.text-success]="step.label === 'Joined'">{{ step.value | number }}</strong>
              <span class="text-xs text-content-muted">{{ step.hint }}</span>
            </div>
          }
        </div>
        @if (d.funnel.by_day.length) {
          <div class="grid lg:grid-cols-2 gap-4 mt-4">
            <div>
              <h3 class="text-sm font-semibold text-content-muted">By the day the email went out (last 14 days)</h3>
              <table class="w-full text-sm mt-2">
                <thead class="text-left text-content-muted"><tr><th class="py-1 pr-3">Day</th><th class="pr-3 text-right">Sent</th><th class="pr-3 text-right">Delivered</th><th class="pr-3 text-right">Opened</th><th class="pr-3 text-right">Clicked</th><th class="text-right">Joined</th></tr></thead>
                <tbody>
                  @for (r of d.funnel.by_day; track r.day) {
                    <tr class="border-t border-line"><td class="py-1 pr-3 whitespace-nowrap">{{ r.day | date:'dd/MM/yyyy' }}</td><td class="pr-3 text-right">{{ r.sent }}</td><td class="pr-3 text-right">{{ r.delivered }}</td><td class="pr-3 text-right">{{ r.opened }} <span class="text-content-muted">({{ pct(r.opened, r.sent) }}%)</span></td><td class="pr-3 text-right">{{ r.clicked }} <span class="text-content-muted">({{ pct(r.clicked, r.sent) }}%)</span></td><td class="text-right" [class.text-success]="r.joined">{{ r.joined }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
            <div>
              <h3 class="text-sm font-semibold text-content-muted">By court</h3>
              <table class="w-full text-sm mt-2">
                <thead class="text-left text-content-muted"><tr><th class="py-1 pr-3">Court</th><th class="pr-3 text-right">Sent</th><th class="pr-3 text-right">Opened</th><th class="pr-3 text-right">Clicked</th><th class="text-right">Joined</th></tr></thead>
                <tbody>
                  @for (r of d.funnel.by_court; track r.court) {
                    <tr class="border-t border-line"><td class="py-1 pr-3">{{ r.court }}</td><td class="pr-3 text-right">{{ r.sent }}</td><td class="pr-3 text-right">{{ r.opened }} <span class="text-content-muted">({{ pct(r.opened, r.sent) }}%)</span></td><td class="pr-3 text-right">{{ r.clicked }} <span class="text-content-muted">({{ pct(r.clicked, r.sent) }}%)</span></td><td class="text-right" [class.text-success]="r.joined">{{ r.joined }}</td></tr>
                  } @empty { <tr><td colspan="5" class="py-2 text-content-muted">No court on the rows sent so far.</td></tr> }
                </tbody>
              </table>
            </div>
          </div>
        }
      </section>

      <section class="rounded-card border border-line bg-surface-raised p-5 mt-4 flex flex-wrap items-center gap-4">
        <div class="flex-1 min-w-[14rem]">
          <h2 class="font-semibold">Scheduled sending is {{ d.paused ? 'paused' : 'on' }}</h2>
          <p class="text-sm text-content-muted">From {{ d.from_address }}. Sent at about 10:30 am, Monday to Saturday.</p>
          @if (d.focus) {
            <p class="text-sm mt-1" [class.text-warning]="d.queued_in_focus === 0" [class.text-content-muted]="d.queued_in_focus !== 0">
              Focus: <strong class="text-content">{{ d.focus }}</strong> · {{ d.queued_in_focus | number }} waiting there@if (d.queued_in_focus === 0) {: change or clear the focus to continue}.
            </p>
          }
          @if (sendingNow() || d.sending) {
            <p class="text-sm text-brand mt-1" role="status"><mat-icon class="material-icons-outlined align-middle text-base animate-pulse">schedule_send</mat-icon> Sending now… {{ d.sent_today }} sent today.</p>
          } @else if (d.counts.queued === 0) {
            <p class="text-sm text-warning mt-1">Nobody is waiting to be invited. Upload a CSV of contacts below and the next morning's batch (or <em>Send now</em>) will go out.</p>
          } @else if (remainingToday() === 0) {
            <p class="text-sm text-content-muted mt-1">Today's number has gone out; the next {{ d.daily_limit }} go tomorrow morning.</p>
          }
        </div>
        <label class="text-sm flex items-center gap-2">Per day
          <input class="vs-input w-20" type="number" min="0" [max]="d.max_daily_limit" [(ngModel)]="limit" />
        </label>
        <label class="text-sm flex items-center gap-2" title="Court by court: while set, only contacts whose city or court matches go out">Focus
          <input class="vs-input w-44" [(ngModel)]="focus" maxlength="200" placeholder="city or court, e.g. Prayagraj" />
        </label>
        <button mat-stroked-button (click)="save({ daily_limit: limit, focus: focus })">Save</button>
        <button mat-stroked-button [color]="d.paused ? 'primary' : 'warn'" (click)="save({ paused: !d.paused })">
          <mat-icon class="material-icons-outlined">{{ d.paused ? 'play_arrow' : 'pause' }}</mat-icon> {{ d.paused ? 'Start scheduled sending' : 'Pause' }}
        </button>
        <button mat-flat-button color="primary" [disabled]="!d.sender_configured || sendingNow() || d.sending || remainingToday() === 0"
                (click)="sendNow()" title="Send the rest of today's number straight away, even while scheduled sending is paused">
          <mat-icon class="material-icons-outlined">send</mat-icon> Send now{{ remainingToday() ? ' (' + remainingToday() + ')' : '' }}
        </button>
      </section>

      <div class="grid lg:grid-cols-2 gap-4 mt-4">
        <section class="rounded-card border border-line bg-surface-raised p-5">
          <h2 class="font-semibold">Add contacts</h2>
          <p class="text-sm text-content-muted mt-1">A CSV with a header row: <code>email</code> (required), <code>name</code>, <code>mobile</code>, <code>city</code>, <code>court</code>, <code>source</code>.
            The source (where the address is publicly listed) is printed in the email; give it per row or for the whole file below.</p>
          <label class="block text-sm mt-3">Source for rows without one
            <input class="vs-input w-full mt-1" [(ngModel)]="source" maxlength="300" placeholder="e.g. the Delhi High Court Bar Association directory" />
          </label>
          <div class="flex flex-wrap items-center gap-2 mt-3">
            <input #csv type="file" accept=".csv,text/csv" hidden (change)="upload(csv)" />
            <button mat-flat-button color="primary" [disabled]="uploading()" (click)="csv.click()"><mat-icon class="material-icons-outlined">upload_file</mat-icon> {{ uploading() ? 'Adding…' : 'Upload CSV' }}</button>
          </div>
          @if (report(); as r) {
            <p class="text-sm mt-3" role="status"><strong>{{ r.added }} added.</strong>
              Not added: {{ r.duplicate }} already listed, {{ r.member }} already members, {{ r.unsubscribed }} unsubscribed or bounced before, {{ r.invalid }} not valid, {{ r.no_source }} without a source.</p>
          }
        </section>
        <section class="rounded-card border border-line bg-surface-raised p-5">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="font-semibold flex-1">The email</h2>
            <button mat-stroked-button [disabled]="!d.sender_configured" (click)="sendTest()"><mat-icon class="material-icons-outlined">send</mat-icon> Send me a test</button>
          </div>
          @if (preview(); as html) {
            <iframe class="mt-3 w-full h-[28rem] rounded-lg border border-line bg-white" [srcdoc]="html" title="Invitation email preview" sandbox=""></iframe>
          }
        </section>
      </div>

      <section class="rounded-card border border-line bg-surface-raised p-5 mt-4">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-semibold flex-1">Contacts <span class="text-content-muted font-normal text-sm">{{ contacts()?.total ?? 0 }} shown</span></h2>
          <input class="vs-input w-56" type="search" placeholder="Search name, email or mobile" [ngModel]="query()" (ngModelChange)="search($event)" />
          <select class="vs-input" [ngModel]="statusFilter()" (ngModelChange)="filterStatus($event)" aria-label="Status">
            <option value="">All statuses</option>
            @for (s of statuses; track s) { <option [value]="s">{{ statusLabel[s] }} ({{ d.counts[s] }})</option> }
          </select>
          <a mat-stroked-button [href]="csvUrl()" target="_blank" rel="noopener"><mat-icon class="material-icons-outlined">download</mat-icon> CSV</a>
        </div>
        <div class="overflow-x-auto mt-3">
          <table class="w-full text-sm">
            <thead class="text-left text-content-muted"><tr>
              <th class="py-2 pr-3">Name</th><th class="pr-3">Email</th><th class="pr-3">Mobile</th><th class="pr-3">City · Court</th>
              <th class="pr-3">Source</th><th class="pr-3">Status</th><th class="pr-3">Approached on</th><th class="pr-3">Read</th><th></th>
            </tr></thead>
            <tbody>
              @for (c of contacts()?.items ?? []; track c.id) {
                <tr class="border-t border-line align-top" [class.opacity-60]="c.status === 'removal_requested' || c.status === 'unsubscribed'">
                  <td class="py-2 pr-3 whitespace-nowrap">{{ c.name || '—' }}</td>
                  <td class="pr-3">{{ c.email }}</td>
                  <td class="pr-3 whitespace-nowrap">{{ c.mobile || '—' }}</td>
                  <td class="pr-3 whitespace-nowrap">{{ c.city || '—' }}@if (c.court) { · {{ c.court }} }</td>
                  <td class="pr-3 max-w-[14rem] truncate" [title]="c.source">{{ c.source }}</td>
                  <td class="pr-3 whitespace-nowrap">
                    <span class="vs-chip" [class.vs-chip--danger]="c.status === 'bounced' || c.status === 'unsubscribed' || c.status === 'removal_requested'"
                          [class.vs-chip--success]="c.status === 'joined'">{{ statusLabel[c.status] }}</span>
                    @if (c.removal_requested_at) { <div class="text-xs text-danger mt-1">{{ c.removal_requested_at | date:'dd/MM/yyyy' }}@if (c.removal_note) { · {{ c.removal_note }} }</div> }
                    @if (c.last_error && c.status === 'bounced') { <div class="text-xs text-content-muted mt-1 max-w-[14rem] truncate" [title]="c.last_error">{{ c.last_error }}</div> }
                  </td>
                  <td class="pr-3 whitespace-nowrap">{{ c.sent_at ? (c.sent_at | date:'dd/MM/yyyy, h:mm a') : '—' }}</td>
                  <td class="pr-3 whitespace-nowrap text-xs">
                    @if (c.clicked_at) { <span class="text-success" [title]="'Clicked ' + (c.clicked_at | date:'dd/MM/yyyy, h:mm a')">Clicked {{ c.clicked_at | date:'dd/MM' }}</span> }
                    @else if (c.opened_at) { <span [title]="'Opened ' + (c.opened_at | date:'dd/MM/yyyy, h:mm a')">Opened {{ c.opened_at | date:'dd/MM' }}</span> }
                    @else if (c.delivered_at) { <span class="text-content-muted">Delivered</span> }
                    @else { <span class="text-content-muted">—</span> }
                    @if (c.complained_at) { <div class="text-danger">Marked as spam</div> }
                  </td>
                  <td class="whitespace-nowrap text-right">
                    @if (c.status !== 'removal_requested') {
                      <button mat-button class="!min-w-0" (click)="flagRemoval(c)" title="They asked not to be contacted: flag and never email them">Asked to be removed</button>
                    }
                    <button mat-icon-button (click)="erase(c)" title="Erase this contact's details for good"><mat-icon class="material-icons-outlined">delete_forever</mat-icon></button>
                  </td>
                </tr>
              } @empty { <tr><td colspan="9" class="py-3 text-content-muted">No contacts match.</td></tr> }
            </tbody>
          </table>
        </div>
        @if ((contacts()?.total ?? 0) > pageSize) {
          <div class="flex items-center justify-end gap-2 mt-3 text-sm">
            <button mat-stroked-button [disabled]="page() <= 1" (click)="goTo(page() - 1)">Previous</button>
            <span>Page {{ page() }} of {{ pages() }}</span>
            <button mat-stroked-button [disabled]="page() >= pages()" (click)="goTo(page() + 1)">Next</button>
          </div>
        }
      </section>
    } @else { <p class="mt-6 text-content-muted">Loading…</p> }
  `,
})
export class OutreachAdminComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly notify = inject(NotificationService);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly api = `${environment.apiBaseUrl}/platform-admin/outreach`;
  protected readonly o = signal<OutreachOverview | null>(null);
  protected readonly report = signal<ImportReport | null>(null);
  protected readonly preview = signal<SafeHtml | null>(null);
  protected readonly uploading = signal(false);
  /** True from the Send now click until the batch stops growing `sent_today`. */
  protected readonly sendingNow = signal(false);
  protected limit = 50;
  protected focus = '';
  protected source = '';

  protected readonly daysLeft = computed(() => {
    const d = this.o();
    return d && d.daily_limit ? Math.ceil(d.counts.queued / d.daily_limit) : 0;
  });
  /** How many Send now would send: the rest of today's number, capped by the queue. */
  protected readonly remainingToday = computed(() => {
    const d = this.o();
    const waiting = d ? (d.focus ? (d.queued_in_focus ?? 0) : d.counts.queued) : 0;
    return d ? Math.max(0, Math.min(d.daily_limit - d.sent_today, waiting)) : 0;
  });
  protected readonly joinRate = computed(() => {
    const d = this.o();
    const invited = d ? d.counts.sent + d.counts.joined + d.counts.unsubscribed + d.counts.bounced : 0;
    return invited ? Math.round((d!.counts.joined / invited) * 100) : 0;
  });
  /** Sent → delivered → opened → clicked → joined, each as a share of those sent. */
  protected readonly funnelSteps = computed(() => {
    const t = this.o()?.funnel.total;
    if (!t) return [];
    const share = (n: number) => `${this.pct(n, t.sent)}% of sent`;
    return [
      { label: 'Sent', value: t.sent, hint: `${t.bounced} bounced · ${t.complained} marked as spam` },
      { label: 'Delivered', value: t.delivered, hint: share(t.delivered) },
      { label: 'Opened', value: t.opened, hint: share(t.opened) },
      { label: 'Clicked', value: t.clicked, hint: share(t.clicked) },
      { label: 'Joined', value: t.joined, hint: `${t.joined_via_email} through the email's link` },
    ];
  });

  protected pct(part: number, whole: number): number {
    return whole ? Math.round((part / whole) * 100) : 0;
  }

  // Contacts list
  protected readonly contacts = signal<ContactPage | null>(null);
  protected readonly query = signal('');
  protected readonly statusFilter = signal<ContactStatus | ''>('');
  protected readonly page = signal(1);
  protected readonly pageSize = 50;
  protected readonly statuses: ContactStatus[] = ['queued', 'sent', 'joined', 'unsubscribed', 'bounced', 'skipped', 'removal_requested'];
  protected readonly statusLabel = STATUS_LABEL;
  protected readonly pages = computed(() => Math.max(1, Math.ceil((this.contacts()?.total ?? 0) / this.pageSize)));
  protected readonly csvUrl = computed(() => {
    const p = new URLSearchParams();
    if (this.query().trim()) p.set('q', this.query().trim());
    if (this.statusFilter()) p.set('status', this.statusFilter());
    const qs = p.toString();
    return `${this.api}/contacts.csv${qs ? '?' + qs : ''}`;
  });
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  async ngOnInit(): Promise<void> {
    await Promise.all([this.load(), this.loadContacts()]);
    try {
      const html = await firstValueFrom(this.http.get(`${this.api}/preview`, { responseType: 'text' }));
      // Our own server-built email, shown in a sandboxed frame (no scripts).
      this.preview.set(this.sanitizer.bypassSecurityTrustHtml(html));
    } catch { /* preview optional */ }
  }

  async load(): Promise<void> {
    try {
      const d = await firstValueFrom(this.http.get<OutreachOverview>(this.api));
      this.o.set(d);
      this.limit = d.daily_limit;
      this.focus = d.focus ?? '';
    } catch { /* toast shown */ }
  }

  async loadContacts(): Promise<void> {
    const params: Record<string, string> = { page: String(this.page()), size: String(this.pageSize) };
    if (this.query().trim()) params['q'] = this.query().trim();
    if (this.statusFilter()) params['status'] = this.statusFilter();
    try {
      this.contacts.set(await firstValueFrom(this.http.get<ContactPage>(`${this.api}/contacts`, { params })));
    } catch { /* toast shown */ }
  }

  protected search(value: string): void {
    this.query.set(value);
    this.page.set(1);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => void this.loadContacts(), 300);
  }

  protected filterStatus(value: ContactStatus | ''): void {
    this.statusFilter.set(value);
    this.page.set(1);
    void this.loadContacts();
  }

  protected goTo(page: number): void {
    this.page.set(page);
    void this.loadContacts();
  }

  protected async flagRemoval(c: Contact): Promise<void> {
    const note = window.prompt(`Flag ${c.name || c.email} as "asked to be removed"? They will never be emailed again. Add a note (how and when they asked):`, '');
    if (note === null) return;
    try {
      await firstValueFrom(this.http.post<Contact>(`${this.api}/contacts/${c.id}/removal-request`, { note: note.trim() || null }));
      this.notify.success('Flagged. The address is on the do-not-email list.');
      await Promise.all([this.load(), this.loadContacts()]);
    } catch (err) {
      this.notify.error(problemMessage(err, 'Could not flag the contact.'));
    }
  }

  protected async erase(c: Contact): Promise<void> {
    if (!window.confirm(`Erase ${c.name || c.email} for good? Name, address and mobile are deleted; the address stays on the do-not-email list.`)) return;
    try {
      await firstValueFrom(this.http.delete(`${this.api}/contacts/${c.id}`));
      this.notify.success('Erased.');
      await Promise.all([this.load(), this.loadContacts()]);
    } catch (err) {
      this.notify.error(problemMessage(err, 'Could not erase the contact.'));
    }
  }

  protected async save(change: { paused?: boolean; daily_limit?: number; focus?: string }): Promise<void> {
    if (change.paused === false && !window.confirm('Start sending invitation emails? Each address is invited once, at most the daily number each morning.')) return;
    try {
      const d = await firstValueFrom(this.http.patch<OutreachOverview>(`${this.api}/settings`, change));
      this.o.set(d);
      this.limit = d.daily_limit;
      this.focus = d.focus ?? '';
      this.notify.success(change.paused === undefined ? (d.focus ? `Saved. Sending only to ${d.focus}.` : 'Saved.') : d.paused ? 'Sending paused.' : 'Sending is on.');
    } catch { /* toast shown */ }
  }

  protected async upload(input: HTMLInputElement): Promise<void> {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    if (this.source.trim()) form.append('source', this.source.trim());
    this.uploading.set(true);
    try {
      this.report.set(await firstValueFrom(this.http.post<ImportReport>(`${this.api}/contacts`, form)));
      await Promise.all([this.load(), this.loadContacts()]);
    } catch (err) {
      this.notify.error(problemMessage(err, 'Could not read that file.'));
    } finally { this.uploading.set(false); }
  }

  protected async sendTest(): Promise<void> {
    try {
      const r = await firstValueFrom(this.http.post<{ sent_to: string }>(`${this.api}/test`, {}));
      this.notify.success(`Test sent to ${r.sent_to}.`);
    } catch (err) {
      this.notify.error(problemMessage(err, 'The test could not be sent.'));
    }
  }

  protected async sendNow(): Promise<void> {
    const n = this.remainingToday();
    if (!window.confirm(`Send ${n} invitation${n === 1 ? '' : 's'} now? They go out a few seconds apart over the next few minutes; each address is invited once.`)) return;
    try {
      const r = await firstValueFrom(this.http.post<{ started: boolean; planned: number }>(`${this.api}/send-now`, {}));
      this.notify.success(`Sending ${r.planned} invitation${r.planned === 1 ? '' : 's'}…`);
      this.sendingNow.set(true);
      void this.watchProgress();
    } catch (err) {
      this.notify.error(problemMessage(err, 'Could not start sending.'));
    }
  }

  /** Refresh every 5 s while the batch runs; stop once `sent_today` has not moved for 20 s. */
  private async watchProgress(): Promise<void> {
    let last = this.o()?.sent_today ?? 0;
    let still = 0;
    const started = Date.now();
    while (Date.now() - started < 15 * 60_000) {
      await new Promise(res => setTimeout(res, 5_000));
      await Promise.all([this.load(), this.loadContacts()]);
      const now = this.o()?.sent_today ?? 0;
      still = now === last ? still + 1 : 0;
      last = now;
      if (still >= 4 && !this.o()?.sending) break;
    }
    this.sendingNow.set(false);
    this.notify.success(`Done: ${last} sent today.`);
  }
}

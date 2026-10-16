import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { environment } from '@env/environment';
import { NotificationService } from '@core/services/notification.service';
import { problemMessage } from '@core/http/problem-message';

interface OutreachOverview {
  paused: boolean; daily_limit: number; max_daily_limit: number; sender_configured: boolean; from_address: string;
  sent_today: number; sent_last_7_days: number; suppressed_total: number;
  counts: Record<'queued' | 'sent' | 'joined' | 'unsubscribed' | 'bounced' | 'skipped', number>;
  recent: { email: string; name: string | null; status: string; source: string; sent_at: string | null; updated_at: string }[];
}
type ImportReport = Record<'added' | 'duplicate' | 'member' | 'unsubscribed' | 'invalid' | 'no_source', number>;

/** Platform admin → Outreach: the daily invitation emails to non-members. */
@Component({
  selector: 'app-outreach-admin',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatButtonModule, MatIconModule],
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

      <section class="rounded-card border border-line bg-surface-raised p-5 mt-4 flex flex-wrap items-center gap-4">
        <div class="flex-1 min-w-[14rem]">
          <h2 class="font-semibold">Sending is {{ d.paused ? 'paused' : 'on' }}</h2>
          <p class="text-sm text-content-muted">From {{ d.from_address }}. Sent at about 10:30 am, Monday to Saturday.</p>
        </div>
        <label class="text-sm flex items-center gap-2">Per day
          <input class="vs-input w-20" type="number" min="0" [max]="d.max_daily_limit" [(ngModel)]="limit" />
        </label>
        <button mat-stroked-button (click)="save({ daily_limit: limit })">Save</button>
        <button mat-flat-button [color]="d.paused ? 'primary' : 'warn'" (click)="save({ paused: !d.paused })">
          <mat-icon class="material-icons-outlined">{{ d.paused ? 'play_arrow' : 'pause' }}</mat-icon> {{ d.paused ? 'Start sending' : 'Pause' }}
        </button>
      </section>

      <div class="grid lg:grid-cols-2 gap-4 mt-4">
        <section class="rounded-card border border-line bg-surface-raised p-5">
          <h2 class="font-semibold">Add contacts</h2>
          <p class="text-sm text-content-muted mt-1">A CSV with a header row: <code>email</code> (required), <code>name</code>, <code>city</code>, <code>court</code>, <code>source</code>.
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
        <h2 class="font-semibold">Recent activity</h2>
        <div class="overflow-x-auto mt-3">
          <table class="w-full text-sm">
            <thead class="text-left text-content-muted"><tr><th class="py-2 pr-3">Email</th><th class="pr-3">Name</th><th class="pr-3">Status</th><th class="pr-3">Source</th><th>When</th></tr></thead>
            <tbody>
              @for (r of d.recent; track r.email) {
                <tr class="border-t border-line">
                  <td class="py-2 pr-3">{{ r.email }}</td><td class="pr-3">{{ r.name || '—' }}</td>
                  <td class="pr-3"><span class="vs-chip capitalize" [class.vs-chip--danger]="r.status === 'bounced' || r.status === 'unsubscribed'">{{ r.status }}</span></td>
                  <td class="pr-3 max-w-[16rem] truncate" [title]="r.source">{{ r.source }}</td>
                  <td class="whitespace-nowrap">{{ (r.sent_at || r.updated_at) | date:'dd/MM/yyyy, h:mm a' }}</td>
                </tr>
              } @empty { <tr><td colspan="5" class="py-3 text-content-muted">Nothing sent yet.</td></tr> }
            </tbody>
          </table>
        </div>
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
  protected limit = 50;
  protected source = '';

  protected readonly daysLeft = computed(() => {
    const d = this.o();
    return d && d.daily_limit ? Math.ceil(d.counts.queued / d.daily_limit) : 0;
  });
  protected readonly joinRate = computed(() => {
    const d = this.o();
    const invited = d ? d.counts.sent + d.counts.joined + d.counts.unsubscribed + d.counts.bounced : 0;
    return invited ? Math.round((d!.counts.joined / invited) * 100) : 0;
  });

  async ngOnInit(): Promise<void> {
    await this.load();
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
    } catch { /* toast shown */ }
  }

  protected async save(change: { paused?: boolean; daily_limit?: number }): Promise<void> {
    if (change.paused === false && !window.confirm('Start sending invitation emails? Each address is invited once, at most the daily number each morning.')) return;
    try {
      const d = await firstValueFrom(this.http.patch<OutreachOverview>(`${this.api}/settings`, change));
      this.o.set(d);
      this.limit = d.daily_limit;
      this.notify.success(change.paused === undefined ? 'Daily number saved.' : d.paused ? 'Sending paused.' : 'Sending is on.');
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
      await this.load();
    } catch (err) {
      this.notify.error(problemMessage(err, 'Could not read that file.'));
    } finally { this.uploading.set(false); }
  }

  protected async sendTest(): Promise<void> {
    try {
      const r = await firstValueFrom(this.http.post<{ sent_to: string }>(`${this.api}/test`, {}));
      this.notify.success(`Test sent to ${r.sent_to}.`);
    } catch { /* toast shown */ }
  }
}

import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { SupportService } from '@core/services/support.service';
import { NotificationService } from '@core/services/notification.service';
import { SupportTicket, TicketPriority } from '@core/models/support.models';

@Component({
  selector: 'app-support-dialog', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, MatButtonModule, MatIconModule],
  template: `
    @if (opened()) {
      <div class="fixed inset-0 z-[1000] bg-black/45 grid place-items-center p-3" (click)="close()">
        <section class="w-full max-w-3xl max-h-[92vh] overflow-auto rounded-card bg-surface-raised shadow-2xl" role="dialog" aria-modal="true" aria-label="VidhiSangh support" (click)="$event.stopPropagation()">
          <header class="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-line bg-surface-raised p-5"><div><h2 class="text-lg font-semibold flex items-center gap-2"><mat-icon class="material-icons-outlined text-brand">contact_support</mat-icon>VidhiSangh Support &amp; Grievance Cell</h2><p class="text-sm text-content-muted mt-1">Report a problem, request a feature, or raise a grievance. Replies remain in this secure thread.</p></div><button mat-icon-button (click)="close()" aria-label="Close"><mat-icon class="material-icons-outlined">close</mat-icon></button></header>
          <nav class="flex border-b border-line px-5"><button class="vs-tab" [class.vs-tab-active]="tab() === 'new'" (click)="tab.set('new')">New request</button><button class="vs-tab" [class.vs-tab-active]="tab() === 'mine'" (click)="showHistory()">My requests @if (tickets().length) { ({{ tickets().length }}) }</button></nav>
          <div class="p-5">
            @if (tab() === 'new') {
              <div class="rounded-xl border border-line p-4"><h3 class="font-semibold"><span class="inline-grid place-items-center w-6 h-6 rounded-full bg-brand text-white text-xs mr-2">1</span>What do you need help with?</h3><input class="vs-input w-full mt-4" maxlength="200" placeholder="Short subject" [(ngModel)]="form.subject" /><div class="grid md:grid-cols-2 gap-4 mt-4"><div><label class="text-xs font-semibold text-content-muted uppercase">Category</label><div class="flex flex-wrap gap-2 mt-2">@for (item of categories; track item.id) { <button class="vs-chip" [class.vs-chip--active]="form.category === item.id" (click)="form.category = item.id"><mat-icon class="material-icons-outlined text-base">{{ item.icon }}</mat-icon>{{ item.label }}</button> }</div></div><div><label class="text-xs font-semibold text-content-muted uppercase">Priority</label><div class="flex flex-wrap gap-2 mt-2">@for (priority of priorities; track priority) { <button class="vs-chip capitalize" [class.vs-chip--active]="form.priority === priority" (click)="form.priority = priority">{{ priority }}</button> }</div></div></div></div>
              <div class="rounded-xl border border-line p-4 mt-4"><h3 class="font-semibold"><span class="inline-grid place-items-center w-6 h-6 rounded-full bg-brand text-white text-xs mr-2">2</span>Describe what happened</h3><p class="text-sm text-content-muted mt-1">Include what you were doing, what you expected, and any steps that reproduce the issue.</p><textarea class="vs-input w-full min-h-48 mt-4" maxlength="20000" [(ngModel)]="form.description" placeholder="Describe the request in detail…"></textarea></div>
              <div class="rounded-lg bg-surface-sunken border border-line p-3 mt-4 text-xs text-content-muted flex gap-2"><mat-icon class="material-icons-outlined text-base">my_location</mat-icon><span>Page context will be included: {{ pageUrl }}</span></div>
              <div class="flex justify-end mt-5"><button mat-flat-button color="primary" [disabled]="saving() || !form.subject.trim() || form.description.trim().length < 5" (click)="submit()"><mat-icon class="material-icons-outlined">send</mat-icon>{{ saving() ? 'Submitting…' : 'Submit request' }}</button></div>
            } @else if (loading()) { <p class="text-content-muted">Loading your requests…</p> }
            @else { <div class="grid gap-3">@for (ticket of tickets(); track ticket.id) { <article class="rounded-xl border border-line p-4"><button class="w-full text-left" (click)="selected.set(selected()?.id === ticket.id ? null : ticket)"><div class="flex flex-wrap items-center gap-2"><strong class="flex-1">{{ ticket.subject }}</strong><span class="vs-chip capitalize">{{ ticket.status.replaceAll('_', ' ') }}</span><span class="vs-chip capitalize" [class.vs-chip--danger]="ticket.priority === 'urgent'">{{ ticket.priority }}</span></div><p class="text-xs text-content-muted mt-1 font-mono">{{ ticket.ticket_number }} · {{ ticket.created_at | date:'dd MMM yyyy, h:mm a' }}</p></button>@if (selected()?.id === ticket.id) { <div class="border-t border-line mt-3 pt-3"><p class="whitespace-pre-line">{{ ticket.description }}</p><div class="mt-4 grid gap-2">@for (message of ticket.messages; track message.id) { <div class="rounded-lg border border-line bg-surface-sunken p-3" [class.border-brand]="message.is_staff"><div class="flex justify-between text-xs"><strong>{{ message.author_name }}@if (message.is_staff) { · Support }</strong><span class="text-content-muted">{{ message.created_at | date:'dd MMM, h:mm a' }}</span></div><p class="mt-1 whitespace-pre-line">{{ message.body }}</p></div> }</div><div class="flex gap-2 mt-3"><input class="vs-input flex-1" placeholder="Add a reply…" [(ngModel)]="replyText" /><button mat-flat-button color="primary" [disabled]="!replyText.trim() || saving()" (click)="reply(ticket)">Reply</button></div></div> }</article> } @empty { <div class="text-center text-content-muted py-10"><mat-icon class="material-icons-outlined text-4xl">support_agent</mat-icon><p>No requests yet.</p></div> }</div> }
          </div>
        </section>
      </div>
    }
  `,
})
export class SupportDialogComponent {
  private readonly support = inject(SupportService); private readonly notify = inject(NotificationService);
  protected readonly opened = signal(false); protected readonly tab = signal<'new' | 'mine'>('new');
  protected readonly tickets = signal<SupportTicket[]>([]); protected readonly selected = signal<SupportTicket | null>(null);
  protected readonly loading = signal(false); protected readonly saving = signal(false); protected replyText = '';
  protected pageUrl = ''; protected form = { subject: '', description: '', category: 'bug', priority: 'medium' as TicketPriority };
  protected readonly priorities: TicketPriority[] = ['low', 'medium', 'high', 'urgent'];
  protected readonly categories = [
    { id: 'bug', label: 'Bug / defect', icon: 'bug_report' }, { id: 'feature_request', label: 'Feature request', icon: 'lightbulb' },
    { id: 'ui_issue', label: 'UI / UX', icon: 'palette' }, { id: 'performance', label: 'Slow page', icon: 'speed' },
    { id: 'data_issue', label: 'Data / report', icon: 'table_chart' }, { id: 'access', label: 'Access', icon: 'lock' },
    { id: 'billing', label: 'Billing', icon: 'receipt_long' }, { id: 'privacy', label: 'Grievance / privacy', icon: 'policy' },
    { id: 'other', label: 'Other', icon: 'more_horiz' },
  ];
  open(): void { this.pageUrl = window.location.href; this.opened.set(true); }
  close(): void { this.opened.set(false); }
  protected async showHistory(): Promise<void> { this.tab.set('mine'); this.loading.set(true); try { this.tickets.set(await firstValueFrom(this.support.mine())); } catch { /* handled */ } finally { this.loading.set(false); } }
  protected async submit(): Promise<void> { this.saving.set(true); try { const created = await firstValueFrom(this.support.create({ ...this.form, page_url: this.pageUrl, browser_context: navigator.userAgent.slice(0, 500) })); this.form = { subject: '', description: '', category: 'bug', priority: 'medium' }; this.notify.success(`${created.ticket_number} submitted to the Grievance Cell.`); await this.showHistory(); } catch { /* handled */ } finally { this.saving.set(false); } }
  protected async reply(ticket: SupportTicket): Promise<void> { if (!this.replyText.trim()) return; this.saving.set(true); try { const updated = await firstValueFrom(this.support.reply(ticket.id, this.replyText.trim())); this.tickets.update((rows) => rows.map((row) => row.id === updated.id ? updated : row)); this.selected.set(updated); this.replyText = ''; } catch { /* handled */ } finally { this.saving.set(false); } }
}

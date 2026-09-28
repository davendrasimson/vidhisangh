import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '@core/auth/auth.service';
import { SupportService } from '@core/services/support.service';
import { NotificationService } from '@core/services/notification.service';
import { AdminAction, PlatformOverview, PlatformPost, PlatformTenant, PlatformUser, SupportTicket, TicketPriority, TicketStatus } from '@core/models/support.models';

type Section = 'overview' | 'members' | 'firms' | 'posts' | 'grievances' | 'actions';

@Component({ selector: 'app-platform-admin', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush, imports: [FormsModule, DatePipe, MatButtonModule, MatIconModule], templateUrl: './platform-admin.component.html' })
export class PlatformAdminComponent implements OnInit {
  private readonly support = inject(SupportService); protected readonly auth = inject(AuthService);
  private readonly notify = inject(NotificationService); private readonly router = inject(Router);
  protected readonly allowed = signal<boolean | null>(null); protected readonly loading = signal(true);
  protected readonly section = signal<Section>('overview'); protected readonly overview = signal<PlatformOverview | null>(null);
  protected readonly users = signal<PlatformUser[]>([]); protected readonly selectedUser = signal<PlatformUser | null>(null);
  protected readonly tenants = signal<PlatformTenant[]>([]); protected readonly posts = signal<PlatformPost[]>([]);
  protected readonly tickets = signal<SupportTicket[]>([]); protected readonly selectedTicket = signal<SupportTicket | null>(null);
  protected readonly actions = signal<AdminAction[]>([]); protected search = ''; protected statusFilter = ''; protected ticketStatus = '';
  protected response = ''; protected replyStatus: TicketStatus = 'waiting_on_user'; protected replyPriority: TicketPriority = 'medium';
  protected readonly sections = [
    { id: 'overview' as const, icon: 'space_dashboard', label: 'Overview' }, { id: 'members' as const, icon: 'group', label: 'Members' },
    { id: 'firms' as const, icon: 'domain', label: 'Firms' }, { id: 'posts' as const, icon: 'dynamic_feed', label: 'Content' },
    { id: 'grievances' as const, icon: 'support_agent', label: 'Grievance Cell' }, { id: 'actions' as const, icon: 'history', label: 'Admin actions' },
  ];

  async ngOnInit(): Promise<void> { try { await firstValueFrom(this.support.adminMe()); this.allowed.set(true); await this.loadOverview(); } catch { this.allowed.set(false); } finally { this.loading.set(false); } }
  protected async choose(next: Section): Promise<void> { this.section.set(next); this.search = ''; await this.reload(); }
  protected async reload(): Promise<void> {
    this.loading.set(true); try {
      if (this.section() === 'overview') await this.loadOverview();
      if (this.section() === 'members') this.users.set(await firstValueFrom(this.support.users(this.search, this.statusFilter)));
      if (this.section() === 'firms') this.tenants.set(await firstValueFrom(this.support.tenants(this.search)));
      if (this.section() === 'posts') this.posts.set(await firstValueFrom(this.support.posts(this.search, true)));
      if (this.section() === 'grievances') this.tickets.set(await firstValueFrom(this.support.tickets(this.ticketStatus)));
      if (this.section() === 'actions') this.actions.set(await firstValueFrom(this.support.actions()));
    } catch { /* handled */ } finally { this.loading.set(false); }
  }
  private async loadOverview(): Promise<void> { this.overview.set(await firstValueFrom(this.support.overview())); }
  protected async inspectUser(user: PlatformUser): Promise<void> { this.selectedUser.set(await firstValueFrom(this.support.user(user.id))); }
  protected async setUserActive(user: PlatformUser, active: boolean): Promise<void> { const reason = window.prompt(`${active ? 'Restore' : 'Block'} ${user.full_name}. Enter the reason for the audit record:`); if (!reason?.trim()) return; try { const updated = await firstValueFrom(this.support.setUserStatus(user.id, active, reason.trim())); this.users.update((rows) => rows.map((row) => row.id === updated.id ? updated : row)); this.selectedUser.set(updated); this.notify.success(active ? 'Member restored.' : 'Member blocked and sessions revoked.'); } catch { /* handled */ } }
  protected async setFirmStatus(firm: PlatformTenant, next: string): Promise<void> { const reason = window.prompt(`Change ${firm.name} to ${next}. Enter the reason:`); if (!reason?.trim()) return; try { const updated = await firstValueFrom(this.support.setTenantStatus(firm.id, next, reason.trim())); this.tenants.update((rows) => rows.map((row) => row.id === updated.id ? updated : row)); this.notify.success(`Firm status changed to ${next}.`); } catch { /* handled */ } }
  protected async moderate(post: PlatformPost, restore: boolean): Promise<void> { const reason = window.prompt(`${restore ? 'Restore' : 'Remove'} this post. Enter the moderation reason:`); if (!reason?.trim()) return; try { const updated = await firstValueFrom(this.support.moderatePost(post.id, restore, reason.trim())); this.posts.update((rows) => rows.map((row) => row.id === updated.id ? updated : row)); this.notify.success(restore ? 'Post restored.' : 'Post removed from feeds.'); } catch { /* handled */ } }
  protected async removeReportedPost(ticket: SupportTicket): Promise<void> { if (!ticket.reported_post_id) return; const reason = window.prompt('Remove this reported post. Enter the moderation reason:', `Grievance ${ticket.ticket_number}`); if (!reason?.trim()) return; try { await firstValueFrom(this.support.moderatePost(ticket.reported_post_id, false, reason.trim())); this.notify.success('Reported post removed from all feeds.'); } catch { /* handled */ } }
  protected async restrictReportedUser(ticket: SupportTicket): Promise<void> { if (!ticket.reported_user_id) return; const answer = window.prompt('Restrict this member from publishing for how many days? (1–365)', '7'); if (answer === null) return; const days = Number(answer); if (!Number.isInteger(days) || days < 1 || days > 365) { this.notify.error('Enter a whole number between 1 and 365.'); return; } const reason = window.prompt('Enter the reason for the restriction:', `Grievance ${ticket.ticket_number}`); if (!reason?.trim()) return; try { await firstValueFrom(this.support.restrictPosting(ticket.reported_user_id, days, reason.trim())); this.notify.success(`Posting restricted for ${days} day${days === 1 ? '' : 's'}.`); } catch { /* handled */ } }
  protected async liftReportedUserRestriction(ticket: SupportTicket): Promise<void> { if (!ticket.reported_user_id) return; try { await firstValueFrom(this.support.restrictPosting(ticket.reported_user_id, null, `Restriction lifted from grievance ${ticket.ticket_number}`)); this.notify.success('Posting restriction lifted.'); } catch { /* handled */ } }
  protected async removeReportedProfile(ticket: SupportTicket): Promise<void> { if (!ticket.reported_user_id) return; const reason = window.prompt('Remove this member’s public network profile. Enter the reason:', `Grievance ${ticket.ticket_number}`); if (!reason?.trim()) return; if (!window.confirm('Remove this public profile? The action is recorded in the admin audit log.')) return; try { await firstValueFrom(this.support.removeNetworkProfile(ticket.reported_user_id, reason.trim())); this.notify.success('Public network profile removed.'); } catch { /* handled */ } }
  protected async blockReportedUser(ticket: SupportTicket): Promise<void> { if (!ticket.reported_user_id) return; const reason = window.prompt('Block this account and revoke all sessions. Enter the reason:', `Grievance ${ticket.ticket_number}`); if (!reason?.trim()) return; if (!window.confirm('Block this account now?')) return; try { await firstValueFrom(this.support.setUserStatus(ticket.reported_user_id, false, reason.trim())); this.notify.success('Member blocked and sessions revoked.'); } catch { /* handled */ } }
  protected openTicket(ticket: SupportTicket): void { this.selectedTicket.set(ticket); this.replyPriority = ticket.priority; this.replyStatus = ticket.status === 'closed' ? 'closed' : 'waiting_on_user'; this.response = ''; }
  protected async updateTicket(assignOnly = false): Promise<void> { const ticket = this.selectedTicket(); if (!ticket) return; try { const updated = await firstValueFrom(this.support.updateTicket(ticket.id, { status: assignOnly ? undefined : this.replyStatus, priority: this.replyPriority, assign_to_me: assignOnly, response: this.response.trim() || undefined })); this.tickets.update((rows) => rows.map((row) => row.id === updated.id ? updated : row)); this.selectedTicket.set(updated); this.response = ''; this.notify.success('Ticket updated.'); await this.loadOverview(); } catch { /* handled */ } }
  protected async logout(): Promise<void> { await this.auth.logout(); await this.router.navigate(['/auth/login'], { queryParams: { returnUrl: '/platform-admin' } }); }
  protected statusLabel(value: string): string { return value.replaceAll('_', ' '); }
}

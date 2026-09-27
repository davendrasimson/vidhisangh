import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MattersService } from '@core/services/matters.service';
import { NotificationService } from '@core/services/notification.service';
import {
  ADVOCATE_ROLE_LABELS,
  Advocate,
  AdvocateRole,
  COURT_LEVEL_LABELS,
  FEE_BASIS_LABELS,
  FEE_EVENT_KIND_LABELS,
  FeeArrangement,
  FeeBasis,
  FeeEvent,
  Hearing,
  MILESTONE_TRIGGER_LABELS,
  Matter,
  MatterDetail,
  MatterStage,
  MatterStatus,
  Milestone,
  MilestoneCreate,
  MilestoneTrigger,
  PartySide,
  Person,
  RATE_BASIS_LABELS,
  RateBasis,
  RetainerPeriod,
  TEAM_END_REASON_LABELS,
  TEAM_ROLE_LABELS,
  Task,
  TeamEndReason,
  TeamMember,
  TeamRole,
  TimelineEntry,
} from '@core/models/matters.models';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';
import { ClientChoice, VsClientPickerComponent } from '@shared/client-picker/vs-client-picker.component';

interface MilestoneDraft {
  label: string;
  trigger: MilestoneTrigger;
  mode: 'amount' | 'percent';
  value: string | number;
  due_on: string;
  due_days: number;
}

@Component({
  selector: 'app-matter-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [VsDateInputComponent, VsClientPickerComponent, FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, MatMenuModule],
  templateUrl: './matter-detail.component.html',
})
export class MatterDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly matters = inject(MattersService);
  private readonly notify = inject(NotificationService);

  private id = '';
  protected readonly matter = signal<MatterDetail | null>(null);
  protected readonly timeline = signal<TimelineEntry[]>([]);
  protected readonly loading = signal(true);
  protected readonly people = signal<Person[]>([]);

  protected readonly statuses: MatterStatus[] = ['open', 'on_hold', 'closed'];
  protected readonly stages: MatterStage[] = [
    'intake', 'filing', 'pleadings', 'evidence', 'arguments', 'judgment', 'closed',
  ];

  protected readonly courtLevels = COURT_LEVEL_LABELS;
  protected readonly advocateRoles = ADVOCATE_ROLE_LABELS;
  protected readonly advocateRoleKeys = Object.keys(ADVOCATE_ROLE_LABELS) as AdvocateRole[];
  protected readonly teamRoles = TEAM_ROLE_LABELS;
  protected readonly teamRoleKeys = Object.keys(TEAM_ROLE_LABELS) as TeamRole[];
  protected readonly endReasons = TEAM_END_REASON_LABELS;
  protected readonly endReasonKeys = Object.keys(TEAM_END_REASON_LABELS) as TeamEndReason[];
  protected readonly rateBases = RATE_BASIS_LABELS;
  protected readonly rateBasisKeys = Object.keys(RATE_BASIS_LABELS) as RateBasis[];
  protected readonly feeBases = FEE_BASIS_LABELS;
  protected readonly feeBasisKeys = Object.keys(FEE_BASIS_LABELS) as FeeBasis[];
  protected readonly triggers = MILESTONE_TRIGGER_LABELS;
  protected readonly triggerKeys = Object.keys(MILESTONE_TRIGGER_LABELS) as MilestoneTrigger[];
  protected readonly eventKinds = FEE_EVENT_KIND_LABELS;

  protected readonly syncing = signal(false);
  /** Opposing counsel we have faced before, keyed by advocate id. */
  protected readonly opponentHistory = signal<Record<string, Matter[]>>({});

  // ── Client link ─────────────────────────────────────────────────
  protected readonly editingClient = signal(false);
  protected clientChoice: ClientChoice | null = null;

  // ── Team ────────────────────────────────────────────────────────
  protected readonly showTeamHistory = signal(false);
  protected readonly activeTeam = computed(() => (this.matter()?.team ?? []).filter((t) => t.is_active));
  protected readonly pastTeam = computed(() => (this.matter()?.team ?? []).filter((t) => !t.is_active).sort((a, b) => (b.to_date ?? '').localeCompare(a.to_date ?? '')));
  protected readonly leadMember = computed(() => this.activeTeam().find((t) => t.role === 'lead_counsel') ?? null);
  protected readonly teamBusy = signal(false);
  protected newMember = { user_id: '', role: 'associate' as TeamRole, from_date: '', rate_basis: '' as RateBasis | '', rate_amount: '' as string | number };
  /** The member whose hand-over panel is open. */
  protected readonly handingOver = signal<TeamMember | null>(null);
  protected handover = { successor_user_id: '', successor_role: '' as TeamRole | '', effective_from: '', reason: 'reassigned' as TeamEndReason, notes: '' };
  protected readonly editingRate = signal<TeamMember | null>(null);
  protected rateEdit = { rate_basis: '' as RateBasis | '', rate_amount: '' as string | number };

  // ── Fees ────────────────────────────────────────────────────────
  protected readonly currentArrangement = computed(() => {
    const all = this.matter()?.fee_arrangements ?? [];
    return all.find((a) => a.is_active && !a.effective_to) ?? all.find((a) => a.is_active) ?? null;
  });
  protected readonly pastArrangements = computed(() => {
    const cur = this.currentArrangement();
    return (this.matter()?.fee_arrangements ?? []).filter((a) => a.id !== cur?.id);
  });
  protected readonly showPastArrangements = signal(false);
  protected readonly showFeeForm = signal(false);
  protected readonly feeBusy = signal(false);
  protected fee = this.blankFee();
  protected milestoneDrafts: MilestoneDraft[] = [];
  protected readonly unbilled = computed(() => this.sum('unbilled'));
  protected readonly invoiced = computed(() => this.sum('invoiced'));
  protected readonly waived = computed(() => this.sum('waived'));
  protected readonly eventsNewestFirst = computed(() =>
    [...(this.matter()?.fee_events ?? [])].sort((a, b) => b.occurred_on.localeCompare(a.occurred_on) || b.created_at.localeCompare(a.created_at)));
  protected manualEvent = { description: '', amount: '' as string | number, occurred_on: '' };

  // Per-section add drafts.
  protected party = { name: '', role: '' };
  protected advocate = {
    name: '',
    side: 'ours' as PartySide,
    role: 'arguing_counsel' as AdvocateRole,
    party_represented: '',
    bar_enrolment_number: '',
    firm: '',
  };
  protected hearing = { scheduled_on: '', court: '', purpose: '' };
  protected task = { title: '', due_on: '' };
  protected noteBody = signal('');

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => {
      const id = p.get('id');
      if (id) {
        this.id = id;
        void this.load();
      }
    });
    void this.loadPeople();
  }

  private async loadPeople(): Promise<void> {
    try {
      this.people.set(await firstValueFrom(this.matters.people()));
    } catch { /* non-fatal */ }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [matter, timeline] = await Promise.all([
        firstValueFrom(this.matters.get(this.id)),
        firstValueFrom(this.matters.timeline(this.id)),
      ]);
      this.matter.set(matter);
      this.timeline.set(timeline);
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  /** Re-fetch the matter (team / fees / events are derived server-side). */
  private async refresh(): Promise<void> {
    try {
      this.matter.set(await firstValueFrom(this.matters.get(this.id)));
    } catch { /* handled */ }
  }

  /** Days until the limitation date (negative = overdue), or null. */
  protected limitationDays(): number | null {
    const d = this.matter()?.limitation_date;
    if (!d) return null;
    const ms = new Date(d + 'T00:00:00').getTime() - Date.now();
    return Math.ceil(ms / 86_400_000);
  }

  private patch(changes: Partial<MatterDetail>): void {
    this.matter.update((m) => (m ? { ...m, ...changes } : m));
  }

  protected async setStatus(status: MatterStatus): Promise<void> {
    try {
      this.matter.set(await firstValueFrom(this.matters.update(this.id, { status })));
    } catch {
      /* handled */
    }
  }

  protected async setStage(stage: MatterStage): Promise<void> {
    try {
      // The server may raise fee events on a stage change, so take its copy.
      this.matter.set(await firstValueFrom(this.matters.update(this.id, { stage })));
    } catch {
      /* handled */
    }
  }

  protected async deleteMatter(): Promise<void> {
    try {
      await firstValueFrom(this.matters.remove(this.id));
      this.notify.success('Matter deleted.');
      await this.router.navigate(['/app/matters']);
    } catch {
      /* handled */
    }
  }

  // ── Client link ─────────────────────────────────────────────────
  protected startEditClient(): void {
    const m = this.matter();
    this.clientChoice = m ? { id: m.client_id, name: m.client_name } : null;
    this.editingClient.set(true);
  }

  protected async saveClient(): Promise<void> {
    if (!this.clientChoice) return;
    try {
      this.matter.set(await firstValueFrom(this.matters.update(this.id, {
        client_id: this.clientChoice.id,
        ...(this.clientChoice.id ? {} : { client_name: this.clientChoice.name }),
      })));
      this.editingClient.set(false);
      this.notify.success('Client updated.');
    } catch { /* handled */ }
  }

  // ── Team ────────────────────────────────────────────────────────
  protected personName(id: string | null): string {
    return this.people().find((p) => p.id === id)?.full_name ?? '—';
  }

  protected rateLabel(t: TeamMember): string | null {
    if (t.rate_amount) return `₹${t.rate_amount} ${this.rateBases[t.rate_basis ?? 'hourly'].toLowerCase()} (this matter)`;
    if (t.card_rate_amount) return `₹${t.card_rate_amount} ${this.rateBases[t.card_rate_basis ?? 'hourly'].toLowerCase()}`;
    return null;
  }

  protected async addMember(): Promise<void> {
    if (!this.newMember.user_id || this.teamBusy()) return;
    this.teamBusy.set(true);
    try {
      await firstValueFrom(this.matters.addTeamMember(this.id, {
        user_id: this.newMember.user_id, role: this.newMember.role,
        from_date: this.newMember.from_date || null,
        rate_basis: this.newMember.rate_basis || null,
        rate_amount: this.newMember.rate_amount ? Number(this.newMember.rate_amount) : null,
      }));
      this.newMember = { user_id: '', role: 'associate', from_date: '', rate_basis: '', rate_amount: '' };
      await this.refresh();
    } catch { /* handled */ } finally { this.teamBusy.set(false); }
  }

  protected async changeRole(t: TeamMember, role: TeamRole): Promise<void> {
    if (role === t.role) return;
    try {
      await firstValueFrom(this.matters.updateTeamMember(this.id, t.id, { role }));
      await this.refresh();
    } catch { /* handled */ }
  }

  protected startHandover(t: TeamMember): void {
    this.handover = { successor_user_id: '', successor_role: '', effective_from: '', reason: 'reassigned', notes: '' };
    this.handingOver.set(t);
  }

  protected async confirmHandover(): Promise<void> {
    const t = this.handingOver();
    if (!t || this.teamBusy()) return;
    this.teamBusy.set(true);
    try {
      await firstValueFrom(this.matters.handover(this.id, t.id, {
        successor_user_id: this.handover.successor_user_id || null,
        successor_role: this.handover.successor_role || null,
        effective_from: this.handover.effective_from || null,
        reason: this.handover.reason,
        notes: this.handover.notes.trim() || null,
      }));
      this.handingOver.set(null);
      this.notify.success(this.handover.successor_user_id ? 'Handed over.' : 'Stint ended.');
      await this.refresh();
    } catch { /* handled */ } finally { this.teamBusy.set(false); }
  }

  protected startRateEdit(t: TeamMember): void {
    this.rateEdit = { rate_basis: t.rate_basis ?? '', rate_amount: t.rate_amount ?? '' };
    this.editingRate.set(t);
  }

  protected async saveRate(): Promise<void> {
    const t = this.editingRate();
    if (!t) return;
    try {
      await firstValueFrom(this.matters.updateTeamMember(this.id, t.id, {
        rate_basis: this.rateEdit.rate_basis || null,
        rate_amount: this.rateEdit.rate_amount === '' ? null : Number(this.rateEdit.rate_amount),
      }));
      this.editingRate.set(null);
      await this.refresh();
    } catch { /* handled */ }
  }

  protected async removeMember(t: TeamMember): Promise<void> {
    try {
      await firstValueFrom(this.matters.removeTeamMember(this.id, t.id));
      await this.refresh();
    } catch { /* handled */ }
  }

  // ── Fees ────────────────────────────────────────────────────────
  private sum(status: FeeEvent['status']): number {
    return (this.matter()?.fee_events ?? []).filter((e) => e.status === status).reduce((s, e) => s + Number(e.amount), 0);
  }

  protected money(v: string | number | null | undefined): string {
    if (v === null || v === undefined || v === '') return '—';
    return '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  protected arrangementSummary(a: FeeArrangement): string[] {
    const parts: string[] = [];
    if (a.fixed_fee) parts.push(`Fixed ${this.money(a.fixed_fee)}`);
    if (a.per_hearing_fee) parts.push(`${this.money(a.per_hearing_fee)} per effective hearing`);
    if (a.non_effective_hearing_fee) parts.push(`${this.money(a.non_effective_hearing_fee)} per adjournment`);
    if (a.hourly_rate) parts.push(`${this.money(a.hourly_rate)} per hour`);
    if (a.retainer_amount) parts.push(`${this.money(a.retainer_amount)} ${a.retainer_period?.replace('_', '-')} retainer${a.retainer_includes ? ` (${a.retainer_includes})` : ''}`);
    if (a.fee_cap) parts.push(`capped at ${this.money(a.fee_cap)}`);
    if (a.basis === 'pro_bono') parts.push('No professional fee');
    return parts;
  }

  protected openFeeForm(): void {
    this.fee = this.blankFee();
    this.milestoneDrafts = [];
    this.showFeeForm.set(true);
  }

  protected onBasisChange(): void {
    if (this.fee.basis === 'milestone' && !this.milestoneDrafts.length) this.applyTemplate('litigation');
  }

  /** Common Indian litigation schedule: advance / filing / first hearing / judgment. */
  protected applyTemplate(kind: 'litigation' | 'advance_balance'): void {
    const pct = (label: string, trigger: MilestoneTrigger, value: number): MilestoneDraft =>
      ({ label, trigger, mode: 'percent', value, due_on: '', due_days: 7 });
    this.milestoneDrafts = kind === 'litigation'
      ? [pct('Advance on engagement', 'advance', 30), pct('On filing', 'on_filing', 30), pct('On first effective hearing', 'on_first_hearing', 30), pct('Balance on judgment', 'on_judgment', 10)]
      : [pct('Advance on engagement', 'advance', 50), pct('Balance on closure', 'on_closure', 50)];
  }

  protected addMilestoneRow(): void {
    this.milestoneDrafts = [...this.milestoneDrafts, { label: '', trigger: 'manual', mode: 'amount', value: '', due_on: '', due_days: 7 }];
  }

  protected removeMilestoneRow(i: number): void {
    this.milestoneDrafts = this.milestoneDrafts.filter((_, idx) => idx !== i);
  }

  protected milestonePercentTotal(): number {
    return this.milestoneDrafts.filter((m) => m.mode === 'percent').reduce((s, m) => s + Number(m.value || 0), 0);
  }

  protected async saveFee(): Promise<void> {
    if (this.feeBusy()) return;
    const f = this.fee;
    const num = (v: string | number) => (v === '' || v === null ? null : Number(v));
    const milestones: MilestoneCreate[] = this.milestoneDrafts
      .filter((m) => m.label.trim() && m.value !== '')
      .map((m) => ({
        label: m.label.trim(), trigger: m.trigger, due_days: m.due_days,
        amount: m.mode === 'amount' ? Number(m.value) : null,
        percent: m.mode === 'percent' ? Number(m.value) : null,
        due_on: m.trigger === 'on_date' ? m.due_on || null : null,
      }));
    this.feeBusy.set(true);
    try {
      await firstValueFrom(this.matters.addFeeArrangement(this.id, {
        basis: f.basis, fixed_fee: num(f.fixed_fee), per_hearing_fee: num(f.per_hearing_fee),
        non_effective_hearing_fee: num(f.non_effective_hearing_fee), hourly_rate: num(f.hourly_rate),
        retainer_amount: num(f.retainer_amount), retainer_period: f.retainer_period || null,
        retainer_includes: f.retainer_includes.trim() || null, fee_cap: num(f.fee_cap),
        expenses_billable: f.expenses_billable, gst_applicable: f.gst_applicable,
        agreed_on: f.agreed_on || null, effective_from: f.effective_from || null,
        terms: f.terms.trim() || null, milestones,
      }));
      this.showFeeForm.set(false);
      this.notify.success('Fee arrangement recorded.');
      await this.refresh();
    } catch (err: unknown) {
      const e = err as { error?: { errors?: { msg?: string }[]; detail?: string } };
      const msg = e?.error?.errors?.[0]?.msg?.replace(/^Value error, /, '') ?? e?.error?.detail;
      if (msg) this.notify.error(msg);
    } finally { this.feeBusy.set(false); }
  }

  protected async endArrangement(a: FeeArrangement): Promise<void> {
    try {
      await firstValueFrom(this.matters.updateFeeArrangement(this.id, a.id, { effective_to: new Date().toISOString().slice(0, 10) }));
      await this.refresh();
    } catch { /* handled */ }
  }

  protected async triggerMilestone(m: Milestone): Promise<void> {
    try {
      await firstValueFrom(this.matters.triggerMilestone(this.id, m.id));
      this.notify.success(`"${m.label}" is now due — a fee event has been raised.`);
      await this.refresh();
    } catch { /* handled */ }
  }

  protected async waiveMilestone(m: Milestone): Promise<void> {
    try {
      await firstValueFrom(this.matters.waiveMilestone(this.id, m.id));
      await this.refresh();
    } catch { /* handled */ }
  }

  protected async addManualEvent(): Promise<void> {
    if (!this.manualEvent.description.trim() || !this.manualEvent.amount) return;
    try {
      await firstValueFrom(this.matters.addFeeEvent(this.id, {
        description: this.manualEvent.description.trim(), amount: Number(this.manualEvent.amount),
        occurred_on: this.manualEvent.occurred_on || null,
      }));
      this.manualEvent = { description: '', amount: '', occurred_on: '' };
      await this.refresh();
    } catch { /* handled */ }
  }

  protected async setEventStatus(e: FeeEvent, status: 'unbilled' | 'waived'): Promise<void> {
    try {
      await firstValueFrom(this.matters.setFeeEventStatus(this.id, e.id, status));
      await this.refresh();
    } catch { /* handled */ }
  }

  private blankFee() {
    return {
      basis: 'fixed' as FeeBasis, fixed_fee: '' as string | number, per_hearing_fee: '' as string | number,
      non_effective_hearing_fee: '' as string | number, hourly_rate: '' as string | number,
      retainer_amount: '' as string | number, retainer_period: 'monthly' as RetainerPeriod | '', retainer_includes: '',
      fee_cap: '' as string | number, expenses_billable: true, gst_applicable: true,
      agreed_on: '', effective_from: '', terms: '',
    };
  }

  // ── Parties ────────────────────────────────────────────────────
  protected async addParty(): Promise<void> {
    if (!this.party.name.trim() || !this.party.role.trim()) return;
    try {
      const created = await firstValueFrom(
        this.matters.addParty(this.id, this.party.name.trim(), this.party.role.trim()),
      );
      this.patch({ parties: [...(this.matter()?.parties ?? []), created] });
      this.party = { name: '', role: '' };
    } catch {
      /* handled */
    }
  }

  // ── Advocates on record ────────────────────────────────────────
  /** "CRL.A. 4562/2023" — skips the parts the registry has not given us. */
  protected caseLabel(m: MatterDetail): string | null {
    const year = m.case_year ? `/${m.case_year}` : '';
    if (m.case_type && m.case_number) return `${m.case_type} ${m.case_number}${year}`;
    if (m.case_type) return `${m.case_type}${year}`;
    return m.case_number ? `${m.case_number}${year}` : null;
  }

  /** Counsel filtered to one side of the cause title. */
  protected advocatesFor(side: PartySide): Advocate[] {
    return (this.matter()?.advocates ?? []).filter((a) => a.side === side);
  }

  protected async addAdvocate(): Promise<void> {
    const name = this.advocate.name.trim();
    if (!name) return;
    try {
      const created = await firstValueFrom(
        this.matters.addAdvocate(this.id, {
          name,
          side: this.advocate.side,
          role: this.advocate.role,
          party_represented: this.advocate.party_represented.trim() || null,
          bar_enrolment_number: this.advocate.bar_enrolment_number.trim() || null,
          firm: this.advocate.firm.trim() || null,
        }),
      );
      this.patch({ advocates: [...(this.matter()?.advocates ?? []), created] });
      this.advocate = {
        name: '', side: this.advocate.side, role: 'arguing_counsel',
        party_represented: '', bar_enrolment_number: '', firm: '',
      };
    } catch {
      /* surfaced by the interceptor */
    }
  }

  protected async removeAdvocate(advocate: Advocate): Promise<void> {
    try {
      await firstValueFrom(this.matters.removeAdvocate(this.id, advocate.id));
      this.patch({
        advocates: (this.matter()?.advocates ?? []).filter((a) => a.id !== advocate.id),
      });
    } catch {
      /* surfaced by the interceptor */
    }
  }

  /** Have we faced this opponent before? Useful prep before a hearing. */
  protected async loadOpponentHistory(advocate: Advocate): Promise<void> {
    if (this.opponentHistory()[advocate.id]) return;
    try {
      const matters = await firstValueFrom(
        this.matters.opposingCounselHistory(advocate.name),
      );
      this.opponentHistory.update((h) => ({
        ...h,
        [advocate.id]: matters.filter((m) => m.id !== this.id),
      }));
    } catch {
      /* surfaced by the interceptor */
    }
  }

  // ── eCourts ────────────────────────────────────────────────────
  protected async syncFromECourts(): Promise<void> {
    if (this.syncing()) return;
    this.syncing.set(true);
    try {
      const fresh = await firstValueFrom(this.matters.ecourtsRefresh(this.id));
      this.matter.set(fresh);
      this.notify.success('Synced from eCourts.');
    } catch {
      /* surfaced by the interceptor */
    } finally {
      this.syncing.set(false);
    }
  }

  // ── Hearings ───────────────────────────────────────────────────
  protected async addHearing(): Promise<void> {
    if (!this.hearing.scheduled_on) return;
    try {
      const created = await firstValueFrom(
        this.matters.addHearing(this.id, {
          scheduled_on: this.hearing.scheduled_on,
          court: this.hearing.court.trim() || null,
          purpose: this.hearing.purpose.trim() || null,
        }),
      );
      this.patch({ hearings: [...(this.matter()?.hearings ?? []), created] });
      this.hearing = { scheduled_on: '', court: '', purpose: '' };
    } catch {
      /* handled */
    }
  }

  protected async setHearingStatus(h: Hearing, status: 'held' | 'adjourned'): Promise<void> {
    try {
      await firstValueFrom(this.matters.updateHearing(h.id, { status }));
      // A held/adjourned hearing may raise a per-hearing fee event.
      await this.refresh();
    } catch {
      /* handled */
    }
  }

  protected async prepareHearing(h: Hearing): Promise<void> {
    const due = h.scheduled_on.slice(0, 10);
    const existing = new Set((this.matter()?.tasks ?? []).map((t) => t.title));
    const label = h.purpose || due;
    const tasks = [
      `Hearing pack: review pleadings and latest order — ${label}`,
      `Hearing pack: verify authorities and statutory provisions — ${label}`,
      `Hearing pack: arrange indexed documents and court copies — ${label}`,
      `Hearing pack: confirm appearance and client instructions — ${label}`,
    ].filter((title) => !existing.has(title));
    try {
      await Promise.all(tasks.map((title) => firstValueFrom(this.matters.addTask(this.id, title, due))));
      this.notify.success(tasks.length ? `${tasks.length} hearing preparation tasks added.` : 'The hearing preparation pack already exists.');
      await this.refresh();
    } catch { /* handled */ }
  }

  // ── Tasks ──────────────────────────────────────────────────────
  protected async addTask(): Promise<void> {
    if (!this.task.title.trim()) return;
    try {
      const created = await firstValueFrom(
        this.matters.addTask(this.id, this.task.title.trim(), this.task.due_on || null),
      );
      this.patch({ tasks: [...(this.matter()?.tasks ?? []), created] });
      this.task = { title: '', due_on: '' };
    } catch {
      /* handled */
    }
  }

  protected async toggleTask(t: Task): Promise<void> {
    try {
      const updated = await firstValueFrom(this.matters.setTaskDone(t.id, t.status !== 'done'));
      this.patch({ tasks: (this.matter()?.tasks ?? []).map((x) => (x.id === t.id ? updated : x)) });
    } catch {
      /* handled */
    }
  }

  // ── Notes ──────────────────────────────────────────────────────
  protected async addNote(): Promise<void> {
    const body = this.noteBody().trim();
    if (!body) return;
    try {
      const created = await firstValueFrom(this.matters.addNote(this.id, body));
      this.patch({ notes: [...(this.matter()?.notes ?? []), created] });
      this.noteBody.set('');
    } catch {
      /* handled */
    }
  }
}

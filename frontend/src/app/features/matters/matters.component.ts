import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, KeyValuePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MattersService } from '@core/services/matters.service';
import { NotificationService } from '@core/services/notification.service';
import {
  COURT_LEVEL_LABELS,
  CourtLevel,
  ECourtsCase,
  Matter,
  MatterCustomFieldType,
  MatterFieldSettings,
  MatterStatus,
  MatterType,
  Person,
  TEAM_END_REASON_LABELS,
  TEAM_ROLE_LABELS,
  TeamEndReason,
  TeamRole,
  WorkloadRow,
} from '@core/models/matters.models';
import { AuthService } from '@core/auth/auth.service';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';
import { ClientChoice, VsClientPickerComponent } from '@shared/client-picker/vs-client-picker.component';

type Filter = 'all' | MatterStatus | 'hearing_soon';

const MINE_KEY = 'vs_matters_mine_only';
function readMine(): boolean {
  try { return typeof localStorage !== 'undefined' && localStorage.getItem(MINE_KEY) === '1'; } catch { return false; }
}

@Component({
  selector: 'app-matters',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [VsDateInputComponent, VsClientPickerComponent, DatePipe, KeyValuePipe, FormsModule, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './matters.component.html',
})
export class MattersComponent implements OnInit {
  private readonly matters = inject(MattersService);
  private readonly notify = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(AuthService);

  protected readonly courtLevels = COURT_LEVEL_LABELS;
  protected readonly courtLevelKeys = Object.keys(COURT_LEVEL_LABELS) as CourtLevel[];
  protected readonly endReasons = TEAM_END_REASON_LABELS;
  protected readonly endReasonKeys = Object.keys(TEAM_END_REASON_LABELS) as TeamEndReason[];

  protected readonly list = signal<Matter[]>([]);
  protected readonly loading = signal(true);
  protected readonly filter = signal<Filter>('all');
  protected readonly search = signal('');
  /** Only matters I lead, am assigned to or am on the team of (remembered on this device). */
  protected readonly mineOnly = signal(readMine());
  /** Colleagues who can be lead counsel / on a team. */
  protected readonly people = signal<Person[]>([]);

  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected form = this.blank();
  /** A client picked from the master (or typed) for the new matter. */
  protected client: ClientChoice | null = null;

  // ─── eCourts import ───────────────────────────────────────────────
  protected readonly showImport = signal(false);
  protected readonly looking = signal(false);
  protected readonly importing = signal(false);
  protected readonly preview = signal<ECourtsCase | null>(null);
  protected readonly lookupError = signal<string | null>(null);
  protected lookup = this.blankLookup();
  protected importClient: ClientChoice | null = null;

  // ─── Reassign (someone left / practice reorganised) ──────────────
  protected readonly showTransfer = signal(false);
  protected readonly transferring = signal(false);
  protected transfer = { from_user_id: '', to_user_id: '', effective_from: '', reason: 'left_firm' as TeamEndReason, notes: '' };

  /** Client-side filtering, so typing feels instant on a loaded page. */
  protected readonly visible = computed(() => {
    const q = this.search().trim().toLowerCase();
    const f = this.filter();
    return this.list().filter((m) => {
      if (f === 'hearing_soon' && !this.isHearingSoon(m)) return false;
      if (f !== 'all' && f !== 'hearing_soon' && m.status !== f) return false;
      if (!q) return true;
      return [
        m.title, m.client_name, m.matter_number, m.cnr_number, m.lead_counsel_name,
        m.case_type, m.case_number, this.caseLabel(m), m.court_establishment, m.court, m.cause_title,
        m.practice_area, m.description, m.state, m.district, m.coram,
      ].some((v) => (v ?? '').toLowerCase().includes(q));
    });
  });

  protected readonly hearingSoonCount = computed(() => this.list().filter((m) => this.isHearingSoon(m)).length);
  protected readonly openCount = computed(() => this.list().filter((m) => m.status === 'open').length);
  protected readonly highPriorityCount = computed(() => this.list().filter((m) => m.status !== 'closed' && m.priority === 'high').length);
  protected readonly limitationCount = computed(() => this.list().filter((m) => {
    const days = this.daysUntil(m.limitation_date);
    return m.status !== 'closed' && days !== null && days >= 0 && days <= 30;
  }).length);
  protected readonly loadError = signal(false);
  protected readonly showFieldSettings = signal(false);
  protected readonly fieldSettings = signal<MatterFieldSettings | null>(null);
  protected readonly fieldBusy = signal(false);
  protected newSection = { name: '', description: '' };
  protected newField = this.blankField();
  protected readonly customFieldTypes: Array<{ value: MatterCustomFieldType; label: string }> = [
    { value: 'text', label: 'Text' }, { value: 'multiline', label: 'Multi-line text' },
    { value: 'rich_text', label: 'Rich formatted text' }, { value: 'number', label: 'Number' },
    { value: 'amount', label: 'Amount' }, { value: 'dropdown', label: 'Drop-down list' },
    { value: 'multi_select', label: 'Multi-select list' }, { value: 'date', label: 'Date' },
    { value: 'boolean', label: 'Yes / No' }, { value: 'email', label: 'Email' },
    { value: 'phone', label: 'Phone' }, { value: 'url', label: 'Web link' },
  ];

  async ngOnInit(): Promise<void> {
    // Arriving from a client record: open the form with that client selected.
    const q = this.route.snapshot.queryParamMap;
    if (q.get('client_id') && q.get('client_name')) {
      this.client = { id: q.get('client_id'), name: q.get('client_name')! };
      this.showForm.set(true);
    }
    await Promise.all([this.reload(), this.loadPeople()]);
  }

  protected async openFieldSettings(): Promise<void> {
    this.showFieldSettings.set(true);
    if (this.fieldSettings()) return;
    try { this.fieldSettings.set(await firstValueFrom(this.matters.fieldSettings())); }
    catch { this.showFieldSettings.set(false); }
  }

  protected async addFieldSection(): Promise<void> {
    if (!this.newSection.name.trim() || this.fieldBusy()) return;
    this.fieldBusy.set(true);
    try {
      const created = await firstValueFrom(this.matters.createFieldSection({
        name: this.newSection.name.trim(), description: this.newSection.description.trim() || null,
      }));
      this.fieldSettings.update((s) => s ? { ...s, sections: [...s.sections, created] } : s);
      this.newSection = { name: '', description: '' };
      this.notify.success('Matter section added.');
    } catch { /* surfaced */ } finally { this.fieldBusy.set(false); }
  }

  protected async addCustomField(): Promise<void> {
    if (!this.newField.label.trim() || this.fieldBusy()) return;
    this.fieldBusy.set(true);
    try {
      const options = this.newField.optionsText.split('\n').map((x) => x.trim()).filter(Boolean);
      const created = await firstValueFrom(this.matters.createCustomField({
        label: this.newField.label.trim(), help_text: this.newField.help_text.trim() || null,
        field_type: this.newField.field_type, section_key: this.newField.section_key,
        custom_section_id: this.newField.section_key === 'custom' ? this.newField.custom_section_id || null : null,
        options, is_required: this.newField.is_required, is_encrypted: this.newField.is_encrypted,
        is_masked: this.newField.is_masked, is_reportable: this.newField.is_reportable,
      }));
      this.fieldSettings.update((s) => s ? { ...s, fields: [...s.fields, created] } : s);
      this.newField = this.blankField();
      this.notify.success('Matter field added. It is now available on every matter.');
    } catch { /* surfaced */ } finally { this.fieldBusy.set(false); }
  }

  protected async deleteCustomField(id: string, label: string): Promise<void> {
    if (!confirm(`Remove “${label}” from matters? Existing values stay recoverable in the audit trail.`)) return;
    await firstValueFrom(this.matters.deleteCustomField(id));
    this.fieldSettings.update((s) => s ? { ...s, fields: s.fields.filter((f) => f.id !== id) } : s);
    this.notify.success('Matter field removed.');
  }

  protected fieldSectionLabel(field: { section_key: string; custom_section_id: string | null }): string {
    const settings = this.fieldSettings();
    if (field.section_key === 'custom') return settings?.sections.find((s) => s.id === field.custom_section_id)?.name ?? 'Custom section';
    return settings?.standard_sections[field.section_key] ?? 'Additional information';
  }

  protected needsOptions(): boolean {
    return this.newField.field_type === 'dropdown' || this.newField.field_type === 'multi_select';
  }

  private async loadPeople(): Promise<void> {
    try {
      this.people.set(await firstValueFrom(this.matters.people()));
    } catch { /* non-fatal */ }
  }

  protected setFilter(f: Filter): void {
    this.filter.set(f);
  }

  private isHearingSoon(m: Matter): boolean {
    const days = this.daysUntil(m.next_hearing_date);
    return m.status !== 'closed' && days !== null && days >= 0 && days <= 14;
  }

  protected relativeDate(date: string | null): string {
    const days = this.daysUntil(date);
    if (days === null) return '';
    if (days === 0) return 'Today';
    return days > 0 ? `In ${days} day${days === 1 ? '' : 's'}` : `${-days} day${days === -1 ? '' : 's'} ago`;
  }

  /** Registry number as a practitioner writes it: "W.P.(C) 1234/2024".
   *  Returns the complete label — callers must not append the year again. */
  protected caseLabel(m: Matter): string | null {
    const year = m.case_year ? `/${m.case_year}` : '';
    if (m.case_type && m.case_number) return `${m.case_type} ${m.case_number}${year}`;
    if (m.case_type) return `${m.case_type}${year || ''}`;
    return m.case_number ? `${m.case_number}${year}` : null;
  }

  protected daysUntil(date: string | null): number | null {
    if (!date) return null;
    const [year, month, day] = date.slice(0, 10).split('-').map(Number);
    const today = new Date();
    const diff = Date.UTC(year, month - 1, day) - Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
    return Math.round(diff / 86_400_000);
  }

  protected async toggleMine(on: boolean): Promise<void> {
    this.mineOnly.set(on);
    try { localStorage.setItem(MINE_KEY, on ? '1' : '0'); } catch { /* storage unavailable */ }
    await this.reload();
  }

  protected async reload(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(false);
    try {
      const all: Matter[] = [];
      for (let page = 1; ; page++) {
        const mine = this.mineOnly() ? { user_id: this.auth.user()?.id } : {};
        const batch = await firstValueFrom(this.matters.list(undefined, page, 50, mine));
        all.push(...batch);
        if (batch.length < 50) break;
      }
      this.list.set(all);
    } catch {
      if (this.list().length) {
        this.notify.error('Could not refresh matters. Showing the last loaded information.');
      } else {
        this.loadError.set(true);
      }
    } finally {
      this.loading.set(false);
    }
  }

  // ─── eCourts ──────────────────────────────────────────────────────
  protected async runLookup(): Promise<void> {
    const cnr = this.lookup.cnr_number.trim();
    const hasCase =
      this.lookup.case_type.trim() && this.lookup.case_number.trim() && this.lookup.case_year;
    if ((!cnr && !hasCase) || this.looking()) return;

    this.looking.set(true);
    this.lookupError.set(null);
    this.preview.set(null);
    try {
      this.preview.set(
        await firstValueFrom(
          this.matters.ecourtsLookup(
            cnr
              ? { cnr_number: cnr }
              : {
                  case_type: this.lookup.case_type.trim(),
                  case_number: this.lookup.case_number.trim(),
                  case_year: Number(this.lookup.case_year),
                  state: this.lookup.state.trim() || undefined,
                  district: this.lookup.district.trim() || undefined,
                },
          ),
        ),
      );
    } catch (err: unknown) {
      // Show the server's reason inline — "no provider configured" and
      // "no such case" are different problems and the user should see which.
      const e = err as { error?: { detail?: string }; status?: number };
      this.lookupError.set(
        e?.error?.detail ?? 'Could not reach the eCourts provider.',
      );
    } finally {
      this.looking.set(false);
    }
  }

  protected async confirmImport(): Promise<void> {
    const found = this.preview();
    if (!found || !this.importClient || this.importing()) return;
    this.importing.set(true);
    try {
      const created = await firstValueFrom(
        this.matters.ecourtsImport({
          cnr_number: found.cnr_number ?? undefined,
          case_type: found.case_type ?? undefined,
          case_number: found.case_number ?? undefined,
          case_year: found.case_year ?? undefined,
          client_id: this.importClient.id,
          client_name: this.importClient.id ? undefined : this.importClient.name,
          lead_counsel_id: this.lookup.lead_counsel_id || null,
          our_side_role: this.lookup.our_side_role,
        }),
      );
      this.notify.success(`${created.matter_number} filed from eCourts.`);
      this.list.update((l) => [created, ...l]);
      this.closeImport();
    } catch {
      /* surfaced by the interceptor */
    } finally {
      this.importing.set(false);
    }
  }

  protected closeImport(): void {
    this.showImport.set(false);
    this.preview.set(null);
    this.lookupError.set(null);
    this.lookup = this.blankLookup();
    this.importClient = null;
  }

  // ─── Manual create ────────────────────────────────────────────────
  protected async submit(): Promise<void> {
    const title = this.form.title.trim();
    if (title.length < 2 || !this.client || this.saving()) return;
    this.saving.set(true);
    try {
      const created = await firstValueFrom(
        this.matters.create({
          title,
          client_id: this.client.id,
          client_name: this.client.id ? undefined : this.client.name,
          lead_counsel_id: this.form.lead_counsel_id || null,
          matter_type: this.form.matter_type,
          court_establishment: this.form.court_establishment.trim() || null,
          court_level: this.form.court_level || null,
          cnr_number: this.form.cnr_number.trim().toUpperCase() || null,
          case_type: this.form.case_type.trim() || null,
          case_number: this.form.case_number.trim() || null,
          practice_area: this.form.practice_area.trim() || null,
          description: this.form.description.trim() || null,
          case_year: this.form.case_year ? Number(this.form.case_year) : null,
          next_hearing_date: this.form.next_hearing_date || null,
          limitation_date: this.form.limitation_date || null,
        }),
      );
      this.notify.success(`${created.matter_number} created.`);
      this.form = this.blank();
      this.client = null;
      this.showForm.set(false);
      this.list.update((l) => [created, ...l]);
    } catch {
      /* surfaced by the interceptor */
    } finally {
      this.saving.set(false);
    }
  }

  // ─── Reassign all of one person's matters ─────────────────────────
  /** Who carries what, shown above the reassign form (absent without matter:manage). */
  protected readonly workload = signal<WorkloadRow[] | null>(null);

  protected toggleTransfer(): void {
    const open = !this.showTransfer();
    this.showTransfer.set(open); this.showImport.set(false); this.showForm.set(false);
    if (open) void this.loadWorkload();
  }

  private async loadWorkload(): Promise<void> {
    try { this.workload.set(await firstValueFrom(this.matters.workload())); } catch { this.workload.set(null); }
  }

  protected roleSummary(row: WorkloadRow): string {
    return Object.entries(row.roles)
      .map(([role, n]) => `${TEAM_ROLE_LABELS[role as TeamRole]?.replace(/ \(.*\)$/, '') ?? role} ${n}`)
      .join(' · ');
  }

  protected async runTransfer(): Promise<void> {
    const t = this.transfer;
    if (!t.from_user_id || !t.to_user_id || t.from_user_id === t.to_user_id || this.transferring()) return;
    this.transferring.set(true);
    try {
      const result = await firstValueFrom(this.matters.transfer({
        from_user_id: t.from_user_id, to_user_id: t.to_user_id,
        effective_from: t.effective_from || null, reason: t.reason, notes: t.notes.trim() || null,
      }));
      this.notify.success(result.moved
        ? `${result.moved} matter${result.moved === 1 ? '' : 's'} moved: ${result.matter_numbers.slice(0, 6).join(', ')}${result.matter_numbers.length > 6 ? '…' : ''}`
        : 'That person is not on any open matter.');
      this.showTransfer.set(false);
      this.transfer = { from_user_id: '', to_user_id: '', effective_from: '', reason: 'left_firm', notes: '' };
      await this.reload();
      void this.loadWorkload();
    } catch {
      /* surfaced by the interceptor */
    } finally {
      this.transferring.set(false);
    }
  }

  private blank() {
    return {
      title: '',
      lead_counsel_id: '',
      matter_type: 'litigation' as MatterType,
      case_number: '',
      practice_area: '',
      description: '',
      court_establishment: '',
      court_level: '' as CourtLevel | '',
      cnr_number: '',
      case_type: '',
      case_year: '' as string | number,
      next_hearing_date: '',
      limitation_date: '',
    };
  }

  private blankLookup() {
    return {
      cnr_number: '',
      case_type: '',
      case_number: '',
      case_year: '' as string | number,
      state: '',
      district: '',
      lead_counsel_id: '',
      our_side_role: 'petitioner',
    };
  }

  private blankField() {
    return {
      label: '', help_text: '', field_type: 'text' as MatterCustomFieldType,
      section_key: 'additional', custom_section_id: '', optionsText: '',
      is_required: false, is_encrypted: false, is_masked: false, is_reportable: true,
    };
  }
}

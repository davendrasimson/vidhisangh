import { ChangeDetectionStrategy, Component, computed, effect, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import {
  BUSINESS_TYPE_LABELS,
  ClientFields,
  ClientKind,
  GST_TREATMENTS,
  ReferenceData,
  ValidationIssue,
} from '@core/models/clients.models';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';
import { ClientFormFields } from './client-privacy.models';

/**
 * The client fields, for staff (create/edit) and for the client's own KYC
 * form — same fields, same validation messages. Emits the working copy on
 * every change; the parent decides when to save.
 */
@Component({
  selector: 'vs-client-form',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, VsDateInputComponent],
  templateUrl: './client-form.component.html',
})
export class ClientFormComponent {
  readonly kind = input.required<ClientKind>();
  readonly value = input<ClientFormFields>({});
  readonly reference = input<ReferenceData | null>(null);
  readonly issues = input<ValidationIssue[]>([]);
  /** 'kyc': the client fills it in — no code/status/notes/tags, consent is explicit. */
  readonly mode = input<'staff' | 'kyc'>('staff');
  readonly changed = output<ClientFormFields>();

  protected readonly form = signal<ClientFormFields>({});
  /** "Additional identity details" — collected only where a matter needs them (DPDP minimisation). */
  protected readonly showMore = signal(false);
  protected readonly gstTreatments = GST_TREATMENTS;
  protected readonly businessTypeLabels = BUSINESS_TYPE_LABELS;

  protected readonly tdsSections = computed(() => this.reference()?.tds_sections ?? []);
  protected readonly states = computed(() => this.reference()?.states ?? []);
  protected readonly businessTypes = computed(() => this.reference()?.business_types ?? Object.keys(BUSINESS_TYPE_LABELS));
  protected readonly issueByField = computed(() => {
    const map: Record<string, ValidationIssue> = {};
    for (const i of this.issues()) map[i.field] ??= i;
    return map;
  });

  constructor() {
    // Reset the working copy whenever the parent hands in a new value.
    effect(() => {
      const v = this.value();
      this.form.set({ country: 'India', ...v });
      if (v.date_of_birth || v.father_or_spouse_name || v.occupation) this.showMore.set(true);
    });
  }

  protected set<K extends keyof ClientFormFields>(key: K, val: ClientFormFields[K]): void {
    const next: ClientFormFields = { ...this.form(), [key]: val };
    if (key === 'is_minor' && !val) {
      next.guardian_name = null;
      next.guardian_relation = null;
    }
    // Derivations the user expects to see immediately.
    if (key === 'state') {
      const s = this.states().find((x) => x.name.toLowerCase() === String(val ?? '').toLowerCase());
      next.state_code = s?.code ?? next.state_code ?? null;
    }
    if (key === 'gstin' && val) {
      next.gst_applicable = true;
      if (!next.gst_treatment || next.gst_treatment === 'unregistered') next.gst_treatment = 'registered_regular';
      next.place_of_supply_code = String(val).slice(0, 2);
      if (this.kind() === 'business' && next.reverse_charge == null) next.reverse_charge = true;
    }
    if (key === 'gst_applicable' && !val) {
      next.reverse_charge = false;
    }
    if (key === 'tds_section') {
      const sec = this.tdsSections().find((s) => s.section === val);
      if (sec && (next.tds_rate == null || next.tds_rate === 0)) next.tds_rate = sec.rate;
    }
    if (key === 'tds_applicable' && val && !next.tds_section) {
      next.tds_section = '194J';
      next.tds_rate = this.tdsSections().find((s) => s.section === '194J')?.rate ?? 10;
    }
    this.form.set(next);
    this.changed.emit(next);
  }

  protected issue(field: string): ValidationIssue | undefined {
    return this.issueByField()[field];
  }
}

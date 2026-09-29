import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom, of } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { BillingService } from '@core/services/billing.service';
import { MattersService } from '@core/services/matters.service';
import { ClientsService } from '@core/services/clients.service';
import { AuthService } from '@core/auth/auth.service';
import { NotificationService } from '@core/services/notification.service';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';
import { Matter } from '@core/models/matters.models';
import { ClientSummary } from '@core/models/clients.models';
import {
  BillingReceipt, BillingSummary, Invoice, InvoiceDocumentType, InvoiceFollowUp,
  InvoiceStatus, LineItemCreate, TimeEntry, TimeImportPreview,
} from '@core/models/billing.models';

type Filter = 'all' | 'pending' | InvoiceStatus;
type View = 'invoices' | 'timesheets' | 'followups' | 'receipts';

@Component({
  selector: 'app-billing', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, VsDateInputComponent],
  templateUrl: './billing.component.html',
})
export class BillingComponent implements OnInit {
  private readonly billing = inject(BillingService);
  private readonly mattersService = inject(MattersService);
  private readonly clientsService = inject(ClientsService);
  protected readonly auth = inject(AuthService);
  private readonly notify = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly invoices = signal<Invoice[]>([]);
  protected readonly allInvoices = signal<Invoice[]>([]);
  protected readonly followUps = signal<InvoiceFollowUp[]>([]);
  protected readonly receipts = signal<BillingReceipt[]>([]);
  protected readonly summary = signal<BillingSummary | null>(null);
  protected readonly timeEntries = signal<TimeEntry[]>([]);
  protected readonly matters = signal<Matter[]>([]);
  protected readonly clients = signal<ClientSummary[]>([]);
  protected readonly selectedTime = signal<Set<string>>(new Set());
  protected readonly importPreview = signal<TimeImportPreview | null>(null);
  protected readonly importing = signal(false);
  protected readonly editingTimeId = signal<string | null>(null);
  protected readonly loading = signal(true);
  protected readonly filter = signal<Filter>('all');
  protected readonly view = signal<View>('invoices');
  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected readonly canManageTime = this.auth.hasPermission('invoice:update');
  protected readonly canImportTime = this.auth.hasPermission('invoice:create');
  protected readonly canReadInvoices = this.auth.hasPermission('invoice:read');
  protected readonly canCreateInvoices = this.auth.hasPermission('invoice:create');
  protected timeForm = {
    work_date: new Date().toISOString().slice(0, 10), matter_id: '', client_id: '',
    hours: 1, description: '', activity_type: 'Professional work', billable: true,
  };
  protected timeInvoice = { document_type: 'proforma' as InvoiceDocumentType, tax_rate: 18, due_date: '', notes: '' };
  protected form = {
    client_name: '', client_id: null as string | null, matter_id: null as string | null,
    tax_rate: 18, due_date: '', notes: '', document_type: 'proforma' as InvoiceDocumentType,
  };
  protected readonly rows = signal<LineItemCreate[]>([{ description: '', quantity: 1, unit_price: 0 }]);
  protected readonly filters: Filter[] = ['all', 'pending', 'draft', 'sent', 'paid', 'overdue', 'cancelled'];

  async ngOnInit(): Promise<void> {
    const q = this.route.snapshot.queryParamMap;
    if (q.get('client_name')) this.form.client_name = q.get('client_name')!;
    this.form.client_id = q.get('client_id'); this.form.matter_id = q.get('matter_id');
    if (q.get('section') === 'timesheets' || !this.canReadInvoices) this.view.set('timesheets');
    if (q.get('prepare') === '1') this.showForm.set(true);
    await this.reloadAll();
  }

  protected async selectView(next: View): Promise<void> { this.view.set(next); await this.reloadAll(); }
  protected async setFilter(next: Filter): Promise<void> { this.filter.set(next); await this.loadInvoices(); }

  private async loadInvoices(): Promise<void> {
    if (!this.canReadInvoices) { this.invoices.set([]); return; }
    const f = this.filter();
    this.invoices.set(await firstValueFrom(
      f === 'pending' ? this.billing.pending() : this.billing.list(f === 'all' ? undefined : f),
    ));
  }

  private async reloadAll(): Promise<void> {
    this.loading.set(true);
    try {
      const [all, summary, followUps, receipts, time, matters, clients] = await Promise.all([
        firstValueFrom(this.canReadInvoices ? this.billing.list() : of([] as Invoice[])),
        firstValueFrom(this.canReadInvoices ? this.billing.summary() : of(null)),
        firstValueFrom(this.canReadInvoices ? this.billing.followUps() : of([] as InvoiceFollowUp[])),
        firstValueFrom(this.canReadInvoices ? this.billing.receipts() : of([] as BillingReceipt[])),
        firstValueFrom(this.billing.timeEntries(this.canManageTime)),
        firstValueFrom(this.mattersService.list(undefined, 1, 100)),
        firstValueFrom(this.clientsService.list()),
      ]);
      this.allInvoices.set(all); this.summary.set(summary); this.followUps.set(followUps); this.receipts.set(receipts);
      this.timeEntries.set(time); this.matters.set(matters); this.clients.set(clients);
      await this.loadInvoices();
    } catch { /* handled centrally */ } finally { this.loading.set(false); }
  }

  protected invoiceFor(id: string): Invoice | undefined { return this.allInvoices().find((item) => item.id === id); }
  protected money(v: string | number): string { return `₹${Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`; }
  protected documentLabel(type: InvoiceDocumentType): string {
    return ({ proforma: 'Proforma invoice', tax_invoice: 'Tax invoice', credit_note: 'Credit note' })[type];
  }
  protected addRow(): void { this.rows.update((rows) => [...rows, { description: '', quantity: 1, unit_price: 0 }]); }
  protected removeRow(i: number): void { this.rows.update((rows) => rows.filter((_, index) => index !== i)); }
  protected updateRow(i: number, field: keyof LineItemCreate, value: string): void {
    const next = field === 'description' ? value : Number(value);
    this.rows.update((rows) => rows.map((row, index) => index === i ? { ...row, [field]: next } : row));
  }

  protected async submit(): Promise<void> {
    if (!this.form.client_name.trim() || this.saving()) return;
    this.saving.set(true);
    try {
      const created = this.form.matter_id && this.rows().every((row) => !row.description.trim() || row.unit_price <= 0)
        ? await firstValueFrom(this.billing.prepareMatterInvoice(this.form.matter_id))
        : await firstValueFrom(this.billing.create({
          client_name: this.form.client_name.trim(), client_id: this.form.client_id, matter_id: this.form.matter_id,
          tax_rate: this.form.tax_rate || 0, due_date: this.form.due_date || null,
          notes: this.form.notes.trim() || null, document_type: this.form.document_type,
          line_items: this.rows().filter((row) => row.description.trim() && row.unit_price > 0),
        }));
      this.notify.success(`${created.invoice_number} created.`);
      this.form = { client_name: '', client_id: null, matter_id: null, tax_rate: 18, due_date: '', notes: '', document_type: 'proforma' };
      this.rows.set([{ description: '', quantity: 1, unit_price: 0 }]); this.showForm.set(false);
      await this.router.navigate(['/app/billing', created.id]);
    } catch { /* handled centrally */ } finally { this.saving.set(false); }
  }

  protected hours(minutes: number): string { return `${(minutes / 60).toFixed(minutes % 60 ? 2 : 0)} h`; }
  protected toggleTime(id: string): void {
    this.selectedTime.update((current) => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next; });
  }
  protected selectedEntries(): TimeEntry[] { return this.timeEntries().filter((entry) => this.selectedTime().has(entry.id)); }
  protected hasSelectedStatus(status: TimeEntry['status']): boolean { return this.selectedEntries().some((entry) => entry.status === status); }

  protected async addTime(): Promise<void> {
    if (!this.timeForm.work_date || !this.timeForm.description.trim() || !Number.isFinite(Number(this.timeForm.hours)) || Number(this.timeForm.hours) <= 0 || Number(this.timeForm.hours) > 24 || (!this.timeForm.matter_id && !this.timeForm.client_id) || this.saving()) return;
    this.saving.set(true);
    try {
      const payload = {
        work_date: this.timeForm.work_date, matter_id: this.timeForm.matter_id || null,
        client_id: this.timeForm.client_id || null, duration_minutes: Math.round(Number(this.timeForm.hours) * 60),
        description: this.timeForm.description.trim(), activity_type: this.timeForm.activity_type,
        billable: this.timeForm.billable,
      };
      const editing = this.editingTimeId();
      await firstValueFrom(editing
        ? this.billing.updateTime(editing, payload)
        : this.billing.createTime(payload));
      this.cancelTimeEdit();
      this.notify.success(editing ? 'Draft time updated.' : 'Time saved as draft. Submit it when ready for review.');
      await this.reloadAll();
    } finally { this.saving.set(false); }
  }

  protected editTime(entry: TimeEntry): void {
    this.editingTimeId.set(entry.id);
    this.timeForm = {
      work_date: entry.work_date, matter_id: entry.matter_id || '', client_id: entry.matter_id ? '' : (entry.client_id || ''),
      hours: entry.duration_minutes / 60, description: entry.description,
      activity_type: entry.activity_type, billable: entry.billable,
    };
  }

  protected cancelTimeEdit(): void {
    this.editingTimeId.set(null);
    this.timeForm = {
      work_date: new Date().toISOString().slice(0, 10), matter_id: '', client_id: '',
      hours: 1, description: '', activity_type: 'Professional work', billable: true,
    };
  }

  protected selectTimeMatter(id: string): void { this.timeForm.matter_id = id; if (id) this.timeForm.client_id = ''; }

  protected async deleteTime(entry: TimeEntry): Promise<void> {
    if (!window.confirm('Delete this draft time entry?')) return;
    await firstValueFrom(this.billing.deleteTime(entry.id));
    this.timeEntries.update((items) => items.filter((item) => item.id !== entry.id));
    if (this.editingTimeId() === entry.id) this.cancelTimeEdit();
    this.notify.success('Draft time entry deleted.');
  }

  protected async submitTime(entry: TimeEntry): Promise<void> {
    await firstValueFrom(this.billing.submitTime(entry.id));
    this.notify.success('Time submitted for billing review.'); await this.reloadAll();
  }

  protected async approveSelected(): Promise<void> {
    const ids = this.selectedEntries().filter((entry) => entry.status === 'submitted').map((entry) => entry.id);
    if (!ids.length) return;
    await firstValueFrom(this.billing.approveTime(ids)); this.selectedTime.set(new Set());
    this.notify.success(`${ids.length} time ${ids.length === 1 ? 'entry' : 'entries'} approved.`); await this.reloadAll();
  }

  protected async billSelected(): Promise<void> {
    const ids = this.selectedEntries().filter((entry) => entry.status === 'approved').map((entry) => entry.id);
    if (!ids.length) return;
    const invoice = await firstValueFrom(this.billing.invoiceTime({
      entry_ids: ids, document_type: this.timeInvoice.document_type, tax_rate: this.timeInvoice.tax_rate,
      due_date: this.timeInvoice.due_date || null, notes: this.timeInvoice.notes || null,
    }));
    this.notify.success(`${invoice.invoice_number} created from ${ids.length} time entries.`);
    await this.router.navigate(['/app/billing', invoice.id]);
  }

  protected async chooseTimesheet(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return;
    this.importing.set(true);
    try { this.importPreview.set(await firstValueFrom(this.billing.previewTimeImport(file))); }
    finally { this.importing.set(false); input.value = ''; }
  }

  protected async commitImport(): Promise<void> {
    const preview = this.importPreview(); if (!preview || preview.error_count || this.importing()) return;
    this.importing.set(true);
    try {
      const created = await firstValueFrom(this.billing.commitTimeImport(preview.rows));
      this.notify.success(`${created.length} time entries imported and sent for review.`);
      this.importPreview.set(null); await this.reloadAll();
    } finally { this.importing.set(false); }
  }

  protected async downloadTemplate(): Promise<void> {
    const blob = await firstValueFrom(this.billing.timeImportTemplate());
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = 'vidhisangh-timesheet-template.csv'; link.click(); URL.revokeObjectURL(url);
  }
}

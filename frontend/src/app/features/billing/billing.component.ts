import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { BillingService } from '@core/services/billing.service';
import { NotificationService } from '@core/services/notification.service';
import {
  BillingReceipt, BillingSummary, Invoice, InvoiceDocumentType, InvoiceFollowUp,
  InvoiceStatus, LineItemCreate,
} from '@core/models/billing.models';

type Filter = 'all' | 'pending' | InvoiceStatus;
type View = 'invoices' | 'followups' | 'receipts';

@Component({
  selector: 'app-billing', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './billing.component.html',
})
export class BillingComponent implements OnInit {
  private readonly billing = inject(BillingService);
  private readonly notify = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly invoices = signal<Invoice[]>([]);
  protected readonly allInvoices = signal<Invoice[]>([]);
  protected readonly followUps = signal<InvoiceFollowUp[]>([]);
  protected readonly receipts = signal<BillingReceipt[]>([]);
  protected readonly summary = signal<BillingSummary | null>(null);
  protected readonly loading = signal(true);
  protected readonly filter = signal<Filter>('all');
  protected readonly view = signal<View>('invoices');
  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
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
    if (q.get('prepare') === '1') this.showForm.set(true);
    await this.reloadAll();
  }

  protected async selectView(next: View): Promise<void> { this.view.set(next); await this.reloadAll(); }
  protected async setFilter(next: Filter): Promise<void> { this.filter.set(next); await this.loadInvoices(); }

  private async loadInvoices(): Promise<void> {
    const f = this.filter();
    this.invoices.set(await firstValueFrom(
      f === 'pending' ? this.billing.pending() : this.billing.list(f === 'all' ? undefined : f),
    ));
  }

  private async reloadAll(): Promise<void> {
    this.loading.set(true);
    try {
      const [all, summary, followUps, receipts] = await Promise.all([
        firstValueFrom(this.billing.list()), firstValueFrom(this.billing.summary()),
        firstValueFrom(this.billing.followUps()), firstValueFrom(this.billing.receipts()),
      ]);
      this.allInvoices.set(all); this.summary.set(summary); this.followUps.set(followUps); this.receipts.set(receipts);
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
}

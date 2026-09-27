import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { BillingService } from '@core/services/billing.service';
import { NotificationService } from '@core/services/notification.service';
import { Invoice, InvoiceStatus, LineItemCreate } from '@core/models/billing.models';

type Filter = 'all' | InvoiceStatus;

@Component({
  selector: 'app-billing',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './billing.component.html',
})
export class BillingComponent implements OnInit {
  private readonly billing = inject(BillingService);
  private readonly notify = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly invoices = signal<Invoice[]>([]);
  protected readonly loading = signal(true);
  protected readonly filter = signal<Filter>('all');

  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected form = { client_name: '', client_id: null as string | null, matter_id: null as string | null, tax_rate: 18 as number };
  protected readonly rows = signal<LineItemCreate[]>([{ description: '', quantity: 1, unit_price: 0 }]);

  protected readonly filters: Filter[] = ['all', 'draft', 'sent', 'paid', 'overdue', 'cancelled'];

  async ngOnInit(): Promise<void> {
    const q = this.route.snapshot.queryParamMap;
    if (q.get('client_name')) this.form.client_name = q.get('client_name')!;
    this.form.client_id = q.get('client_id');
    this.form.matter_id = q.get('matter_id');
    if (q.get('prepare') === '1') this.showForm.set(true);
    await this.reload();
  }

  protected async setFilter(f: Filter): Promise<void> {
    this.filter.set(f);
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.loading.set(true);
    try {
      const f = this.filter();
      this.invoices.set(await firstValueFrom(this.billing.list(f === 'all' ? undefined : f)));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected money(v: string | number): string {
    return `₹${Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  }

  // ── Line-item editor ───────────────────────────────────────────
  protected addRow(): void {
    this.rows.update((r) => [...r, { description: '', quantity: 1, unit_price: 0 }]);
  }

  protected removeRow(i: number): void {
    this.rows.update((r) => r.filter((_, idx) => idx !== i));
  }

  protected updateRow(i: number, field: keyof LineItemCreate, value: string): void {
    const next = field === 'description' ? value : Number(value);
    this.rows.update((r) => r.map((row, idx) => (idx === i ? { ...row, [field]: next } : row)));
  }

  protected async submit(): Promise<void> {
    if (!this.form.client_name.trim() || this.saving()) return;
    this.saving.set(true);
    try {
      const created = this.form.matter_id && this.rows().every((r) => !r.description.trim() || r.unit_price <= 0)
        ? await firstValueFrom(this.billing.prepareMatterInvoice(this.form.matter_id))
        : await firstValueFrom(this.billing.create({
          client_name: this.form.client_name.trim(),
          client_id: this.form.client_id,
          matter_id: this.form.matter_id,
          tax_rate: this.form.tax_rate ?? 0,
          line_items: this.rows().filter((r) => r.description.trim() && r.unit_price > 0),
        }));
      this.notify.success(`${created.invoice_number} created.`);
      const matterId = this.form.matter_id;
      this.form = { client_name: '', client_id: null, matter_id: null, tax_rate: 18 };
      this.rows.set([{ description: '', quantity: 1, unit_price: 0 }]);
      this.showForm.set(false);
      await this.reload();
      if (matterId) await this.router.navigate(['/app/billing', created.id]);
    } catch {
      /* handled */
    } finally {
      this.saving.set(false);
    }
  }
}

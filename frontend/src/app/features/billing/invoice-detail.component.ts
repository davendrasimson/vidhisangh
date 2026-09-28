import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { BillingService } from '@core/services/billing.service';
import { PaymentService } from '@core/services/payment.service';
import { NotificationService } from '@core/services/notification.service';
import { BillingBranding, InvoiceDetail, InvoiceStatus } from '@core/models/billing.models';

@Component({
  selector: 'app-invoice-detail', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './invoice-detail.component.html',
  styles: [`
    .document { border-top: 6px solid var(--document-accent, #215dcc); }
    .document.classic { border: 1px solid rgb(var(--vs-border)); border-top: 6px solid var(--document-accent, #215dcc); }
    .document.minimal { border-top-color: transparent; }
    @media print { .no-print { display:none!important; } .document { border:0!important; box-shadow:none!important; } }
  `],
})
export class InvoiceDetailComponent {
  private readonly route = inject(ActivatedRoute);
  protected readonly billing = inject(BillingService);
  private readonly payments = inject(PaymentService);
  private readonly notify = inject(NotificationService);
  private id = '';
  protected readonly invoice = signal<InvoiceDetail | null>(null);
  protected readonly branding = signal<BillingBranding | null>(null);
  protected readonly loading = signal(true);
  protected readonly paying = signal(false);
  protected readonly savingFollowUp = signal(false);
  protected readonly savingReceipt = signal(false);
  protected readonly statuses: InvoiceStatus[] = ['draft', 'sent', 'paid', 'overdue', 'cancelled'];
  protected newItem = { description: '', quantity: 1, unit_price: 0 };
  protected followUp = { channel: 'phone', remark: '', outcome: '', next_follow_up_on: '' };
  protected receipt = { amount: 0, received_on: new Date().toISOString().slice(0, 10), payment_method: 'bank_transfer', reference: '', remarks: '' };
  protected readonly balance = computed(() => { const inv = this.invoice(); return inv ? Number(inv.total) - Number(inv.amount_paid) : 0; });

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      const id = params.get('id'); if (id) { this.id = id; void this.load(); }
    });
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [invoice, branding] = await Promise.all([firstValueFrom(this.billing.get(this.id)), firstValueFrom(this.billing.branding())]);
      this.invoice.set(invoice); this.branding.set(branding); this.receipt.amount = this.balance();
    } catch { /* handled centrally */ } finally { this.loading.set(false); }
  }

  protected money(v: string | number): string { return `₹${Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`; }
  protected title(): string { return ({ proforma: 'PROFORMA INVOICE', tax_invoice: 'TAX INVOICE', credit_note: 'CREDIT NOTE' })[this.invoice()?.document_type || 'tax_invoice']; }
  protected editable(): boolean { return ['draft', 'sent'].includes(this.invoice()?.status || ''); }
  protected paymentLink(): string { return `${window.location.origin}/pay/${this.invoice()?.payment_token || ''}`; }
  protected print(): void { window.print(); }
  protected async copyPaymentLink(): Promise<void> { await navigator.clipboard.writeText(this.paymentLink()); this.notify.success('Payment link copied.'); }

  protected async setStatus(status: InvoiceStatus): Promise<void> {
    try { this.invoice.set(await firstValueFrom(this.billing.update(this.id, { status }))); } catch { /* handled */ }
  }
  protected async addLine(): Promise<void> {
    if (!this.newItem.description.trim() || this.newItem.unit_price <= 0) return;
    try { this.invoice.set(await firstValueFrom(this.billing.addLineItem(this.id, { ...this.newItem }))); this.newItem = { description: '', quantity: 1, unit_price: 0 }; } catch { /* handled */ }
  }
  protected async removeLine(itemId: string): Promise<void> {
    try { this.invoice.set(await firstValueFrom(this.billing.removeLineItem(itemId))); } catch { /* handled */ }
  }
  protected async saveFollowUp(): Promise<void> {
    if (!this.followUp.remark.trim() || this.savingFollowUp()) return;
    this.savingFollowUp.set(true);
    try {
      this.invoice.set(await firstValueFrom(this.billing.addFollowUp(this.id, {
        channel: this.followUp.channel, remark: this.followUp.remark.trim(), outcome: this.followUp.outcome.trim() || null,
        next_follow_up_on: this.followUp.next_follow_up_on || null,
      })));
      this.followUp = { channel: 'phone', remark: '', outcome: '', next_follow_up_on: '' };
      this.notify.success('Follow-up recorded.');
    } catch { /* handled */ } finally { this.savingFollowUp.set(false); }
  }
  protected async saveReceipt(): Promise<void> {
    if (this.receipt.amount <= 0 || this.savingReceipt()) return;
    this.savingReceipt.set(true);
    try {
      this.invoice.set(await firstValueFrom(this.billing.recordReceipt(this.id, {
        amount: this.receipt.amount, received_on: this.receipt.received_on || null,
        payment_method: this.receipt.payment_method, reference: this.receipt.reference.trim() || null,
        remarks: this.receipt.remarks.trim() || null,
      })));
      this.receipt = { amount: this.balance(), received_on: new Date().toISOString().slice(0, 10), payment_method: 'bank_transfer', reference: '', remarks: '' };
      this.notify.success(this.invoice()?.converted_invoice_id ? 'Receipt recorded and tax invoice created automatically.' : 'Receipt recorded.');
    } catch { /* handled */ } finally { this.savingReceipt.set(false); }
  }
  protected async pay(): Promise<void> {
    if (this.balance() <= 0 || this.paying()) return;
    this.paying.set(true);
    try {
      const order = await firstValueFrom(this.billing.pay(this.id)); const result = await this.payments.openCheckout(order);
      if (!result) { this.notify.info(order.provider === 'mock' ? 'Order created. Live checkout opens when Razorpay is configured.' : 'Payment cancelled.'); return; }
      await firstValueFrom(this.payments.verify(order.payment_id, result)); this.invoice.set(await firstValueFrom(this.billing.reconcile(this.id))); this.notify.success('Payment received.');
    } catch { /* handled */ } finally { this.paying.set(false); }
  }
}

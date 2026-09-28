import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { BillingService } from '@core/services/billing.service';
import { PaymentService } from '@core/services/payment.service';
import { NotificationService } from '@core/services/notification.service';
import { PublicInvoice } from '@core/models/billing.models';

@Component({
  selector: 'app-public-invoice', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, MatButtonModule, MatIconModule],
  template: `
    <main class="min-h-screen bg-surface-sunken p-4 md:p-8">
      <div class="max-w-4xl mx-auto">
        <a routerLink="/" class="inline-flex items-center gap-2 font-semibold text-brand mb-5"><mat-icon class="material-icons-outlined">balance</mat-icon>VidhiSangh secure billing</a>
        @if (loading()) { <p>Loading billing document…</p> }
        @else if (invoice(); as inv) {
          <article class="rounded-card bg-white text-slate-900 shadow-card overflow-hidden" [style.border-top]="'7px solid ' + inv.branding.accent_color">
            <div class="p-6 md:p-9">
              <header class="flex justify-between gap-6 border-b border-slate-200 pb-5"><div>@if (inv.branding.logo_url) { <img [src]="inv.branding.logo_url" alt="Firm logo" class="max-h-14 max-w-48 object-contain mb-3" /> }<h1 class="text-xl font-bold">{{ inv.branding.legal_name }}</h1><p class="text-sm text-slate-500 whitespace-pre-line">{{ inv.branding.address }}</p></div><div class="text-right"><p class="font-bold tracking-wide" [style.color]="inv.branding.accent_color">{{ title(inv.document_type) }}</p><p class="font-mono text-lg">{{ inv.invoice_number }}</p><span class="inline-block rounded-full bg-slate-100 px-3 py-1 text-xs capitalize mt-2">{{ inv.status }}</span></div></header>
              <div class="grid sm:grid-cols-2 gap-4 py-5"><div><small class="text-slate-500 uppercase">Bill to</small><p class="font-semibold">{{ inv.client_name }}</p></div><div class="sm:text-right text-sm"><p>Issued {{ inv.issue_date | date:'dd MMM yyyy' }}</p>@if (inv.due_date) { <p>Due {{ inv.due_date | date:'dd MMM yyyy' }}</p> }</div></div>
              <div class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b-2 border-slate-200 text-left"><th class="py-2">Description</th><th class="text-right">Qty</th><th class="text-right">Rate</th><th class="text-right">Amount</th></tr></thead><tbody>@for (item of inv.line_items; track item.id) { <tr class="border-b border-slate-100"><td class="py-3">{{ item.description }}</td><td class="text-right">{{ item.quantity }}</td><td class="text-right">{{ money(item.unit_price) }}</td><td class="text-right">{{ money(item.amount) }}</td></tr> }</tbody></table></div>
              <div class="ml-auto max-w-sm mt-6 text-sm"><div class="flex justify-between py-1"><span>Subtotal</span><span>{{ money(inv.subtotal) }}</span></div><div class="flex justify-between py-1"><span>GST ({{ inv.tax_rate }}%)</span><span>{{ money(inv.tax_amount) }}</span></div><div class="flex justify-between border-y border-slate-200 py-2 text-lg font-bold"><span>Total</span><span>{{ money(inv.total) }}</span></div><div class="flex justify-between py-1"><span>Paid</span><span>{{ money(inv.amount_paid) }}</span></div><div class="flex justify-between py-1 font-semibold"><span>Balance</span><span>{{ money(balance(inv)) }}</span></div></div>
              @if (inv.branding.bank_details) { <div class="mt-6 text-sm"><strong>Payment details</strong><p class="text-slate-600 whitespace-pre-line">{{ inv.branding.bank_details }}</p></div> }
              <footer class="border-t border-slate-200 mt-7 pt-4 text-xs text-slate-500"><p>{{ inv.branding.footer }}</p><a [routerLink]="['/verify/invoice', inv.verification_code]" class="inline-flex items-center gap-1 text-blue-700 mt-2"><mat-icon class="material-icons-outlined text-base">verified_user</mat-icon>Verify authenticity · {{ inv.verification_code }}</a></footer>
            </div>
            @if (balance(inv) > 0 && inv.status !== 'cancelled') { <div class="bg-slate-50 border-t border-slate-200 p-5 flex flex-wrap items-center justify-between gap-3"><div><strong>Amount payable: {{ money(balance(inv)) }}</strong><p class="text-sm text-slate-500">Secure online payment powered by the firm's payment provider.</p></div><button mat-flat-button color="primary" [disabled]="paying()" (click)="pay()"><mat-icon class="material-icons-outlined">lock</mat-icon>{{ paying() ? 'Opening…' : 'Pay securely' }}</button></div> }
          </article>
        } @else { <section class="rounded-card bg-surface-raised p-8"><h1 class="text-xl font-semibold">Document unavailable</h1><p class="text-content-muted mt-2">This payment link is invalid or has expired. Please contact the issuing firm.</p></section> }
      </div>
    </main>
  `,
})
export class PublicInvoiceComponent {
  private readonly route = inject(ActivatedRoute); private readonly billing = inject(BillingService);
  private readonly payments = inject(PaymentService); private readonly notify = inject(NotificationService);
  private token = ''; protected readonly invoice = signal<PublicInvoice | null>(null); protected readonly loading = signal(true); protected readonly paying = signal(false);
  constructor() { this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => { this.token = p.get('token') || ''; void this.load(); }); }
  private async load(): Promise<void> { this.loading.set(true); try { this.invoice.set(await firstValueFrom(this.billing.publicInvoice(this.token))); } catch { this.invoice.set(null); } finally { this.loading.set(false); } }
  protected money(value: string | number): string { return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`; }
  protected balance(inv: PublicInvoice): number { return Number(inv.total) - Number(inv.amount_paid); }
  protected title(type: string): string { return ({ proforma: 'PROFORMA INVOICE', tax_invoice: 'TAX INVOICE', credit_note: 'CREDIT NOTE' } as Record<string, string>)[type] || 'INVOICE'; }
  protected async pay(): Promise<void> { this.paying.set(true); try { const order = await firstValueFrom(this.billing.publicPay(this.token)); const result = await this.payments.openCheckout(order); if (!result) return; this.invoice.set(await firstValueFrom(this.billing.publicVerifyPayment(this.token, order.payment_id, result))); this.notify.success('Payment received. Your tax invoice and receipt have been created.'); } catch { /* handled */ } finally { this.paying.set(false); } }
}

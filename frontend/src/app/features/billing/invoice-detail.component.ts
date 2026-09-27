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
import { InvoiceDetail, InvoiceStatus } from '@core/models/billing.models';

@Component({
  selector: 'app-invoice-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './invoice-detail.component.html',
})
export class InvoiceDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly billing = inject(BillingService);
  private readonly payments = inject(PaymentService);
  private readonly notify = inject(NotificationService);

  private id = '';
  protected readonly invoice = signal<InvoiceDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly paying = signal(false);

  protected readonly statuses: InvoiceStatus[] = ['draft', 'sent', 'paid', 'overdue', 'cancelled'];
  protected newItem = { description: '', quantity: 1, unit_price: 0 };

  protected readonly balance = computed(() => {
    const inv = this.invoice();
    return inv ? Number(inv.total) - Number(inv.amount_paid) : 0;
  });

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => {
      const id = p.get('id');
      if (id) {
        this.id = id;
        void this.load();
      }
    });
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.invoice.set(await firstValueFrom(this.billing.get(this.id)));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected money(v: string | number): string {
    return `₹${Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  }

  protected editable(): boolean {
    const s = this.invoice()?.status;
    return s === 'draft' || s === 'sent';
  }

  protected async setStatus(status: InvoiceStatus): Promise<void> {
    try {
      this.invoice.set(await firstValueFrom(this.billing.update(this.id, { status })));
    } catch {
      /* handled */
    }
  }

  protected async addLine(): Promise<void> {
    if (!this.newItem.description.trim() || this.newItem.unit_price <= 0) return;
    try {
      this.invoice.set(await firstValueFrom(this.billing.addLineItem(this.id, { ...this.newItem })));
      this.newItem = { description: '', quantity: 1, unit_price: 0 };
    } catch {
      /* handled */
    }
  }

  protected async removeLine(itemId: string): Promise<void> {
    try {
      this.invoice.set(await firstValueFrom(this.billing.removeLineItem(itemId)));
    } catch {
      /* handled */
    }
  }

  protected async pay(): Promise<void> {
    if (this.balance() <= 0 || this.paying()) return;
    this.paying.set(true);
    try {
      const order = await firstValueFrom(this.billing.pay(this.id));
      const result = await this.payments.openCheckout(order);
      if (!result) {
        this.notify.info(
          order.provider === 'mock'
            ? 'Order created. Live Razorpay Checkout opens once API keys are configured.'
            : 'Payment cancelled.',
        );
        return;
      }
      await firstValueFrom(this.payments.verify(order.payment_id, result));
      this.invoice.set(await firstValueFrom(this.billing.reconcile(this.id)));
      this.notify.success('Payment received.');
    } catch {
      /* handled */
    } finally {
      this.paying.set(false);
    }
  }
}

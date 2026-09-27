import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { PaymentService } from '@core/services/payment.service';
import { NotificationService } from '@core/services/notification.service';
import { Payment } from '@core/models/payment.models';

@Component({
  selector: 'app-payments',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, MatIconModule, MatButtonModule],
  templateUrl: './payments.component.html',
})
export class PaymentsComponent implements OnInit {
  private readonly payments = inject(PaymentService);
  private readonly notify = inject(NotificationService);

  protected readonly list = signal<Payment[]>([]);
  protected readonly loading = signal(true);
  protected readonly collecting = signal(false);
  protected form = { amount: null as number | null, description: '' };

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.loading.set(true);
    try {
      this.list.set(await firstValueFrom(this.payments.list()));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected rupees(paise: number): string {
    return `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  }

  protected async collect(): Promise<void> {
    const rupees = this.form.amount;
    if (!rupees || rupees < 1 || this.collecting()) return;
    this.collecting.set(true);
    try {
      const order = await firstValueFrom(
        this.payments.createOrder(Math.round(rupees * 100), this.form.description.trim() || undefined),
      );
      const result = await this.payments.openCheckout(order);
      if (!result) {
        // Mock gateway / dismissed: the order still exists as "created".
        this.notify.info(
          order.provider === 'mock'
            ? 'Order created. Live Razorpay Checkout opens once API keys are configured.'
            : 'Payment cancelled.',
        );
      } else {
        const paid = await firstValueFrom(this.payments.verify(order.payment_id, result));
        if (paid.status === 'paid') this.notify.success('Payment received.');
      }
      this.form = { amount: null, description: '' };
      await this.reload();
    } catch {
      /* handled */
    } finally {
      this.collecting.set(false);
    }
  }
}

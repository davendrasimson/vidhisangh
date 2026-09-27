import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { OrderResponse, Payment } from '@core/models/payment.models';

/* Razorpay Checkout injects a global constructor. */
declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

export interface CheckoutResult {
  razorpay_payment_id: string;
  razorpay_signature: string;
}

@Injectable({ providedIn: 'root' })
export class PaymentService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/payments`;
  private scriptPromise: Promise<boolean> | null = null;

  createOrder(amount: number, description?: string, matter_id?: string): Observable<OrderResponse> {
    return this.http.post<OrderResponse>(`${this.api}/orders`, { amount, description, matter_id });
  }

  verify(paymentId: string, result: CheckoutResult): Observable<Payment> {
    return this.http.post<Payment>(`${this.api}/${paymentId}/verify`, result);
  }

  list(): Observable<Payment[]> {
    return this.http.get<Payment[]>(this.api);
  }

  /** Load Razorpay Checkout (external script) once. */
  private loadScript(): Promise<boolean> {
    if (window.Razorpay) return Promise.resolve(true);
    if (!this.scriptPromise) {
      this.scriptPromise = new Promise<boolean>((resolve) => {
        const s = document.createElement('script');
        s.src = 'https://checkout.razorpay.com/v1/checkout.js';
        s.onload = () => resolve(true);
        s.onerror = () => resolve(false);
        document.body.appendChild(s);
      });
    }
    return this.scriptPromise;
  }

  /** Open Razorpay Checkout; resolves with the signed result, or null if
   *  dismissed / unavailable (e.g. the mock gateway has no real checkout). */
  async openCheckout(order: OrderResponse): Promise<CheckoutResult | null> {
    const loaded = await this.loadScript();
    if (!loaded || !window.Razorpay) return null;
    return new Promise<CheckoutResult | null>((resolve) => {
      const rzp = new window.Razorpay!({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        order_id: order.order_id,
        name: 'VidhiSangh',
        description: 'Payment',
        handler: (r: CheckoutResult) =>
          resolve({ razorpay_payment_id: r.razorpay_payment_id, razorpay_signature: r.razorpay_signature }),
        modal: { ondismiss: () => resolve(null) },
      });
      rzp.open();
    });
  }
}

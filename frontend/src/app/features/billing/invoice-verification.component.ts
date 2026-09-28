import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { BillingService } from '@core/services/billing.service';
import { BillingVerification } from '@core/models/billing.models';

@Component({ selector: 'app-invoice-verification', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush, imports: [DatePipe, RouterLink, MatIconModule], template: `
  <main class="min-h-screen bg-surface-sunken grid place-items-center p-4"><section class="w-full max-w-lg rounded-card bg-surface-raised border border-line shadow-card p-7 text-center"><a routerLink="/" class="inline-flex items-center gap-2 text-brand font-semibold"><mat-icon class="material-icons-outlined">balance</mat-icon>VidhiSangh</a>
    @if (loading()) { <p class="mt-8 text-content-muted">Checking document authenticity…</p> }
    @else if (result(); as item) { <div class="mx-auto mt-7 grid place-items-center rounded-full bg-success/10 text-success w-16 h-16"><mat-icon class="material-icons-outlined text-4xl">verified</mat-icon></div><h1 class="text-2xl font-bold mt-4">Authentic document</h1><p class="text-content-muted mt-1">This record matches the secure billing register.</p><dl class="grid grid-cols-2 text-left gap-y-3 mt-7 border-y border-line py-5"><dt class="text-content-muted">Document</dt><dd class="font-medium capitalize">{{ label(item.document_type) }}</dd><dt class="text-content-muted">Number</dt><dd class="font-mono">{{ item.number }}</dd><dt class="text-content-muted">Issued by</dt><dd>{{ item.firm }}</dd>@if (item.client_name) { <dt class="text-content-muted">Client</dt><dd>{{ item.client_name }}</dd> }<dt class="text-content-muted">Amount</dt><dd class="font-semibold">{{ money(item.total) }}</dd><dt class="text-content-muted">Status</dt><dd class="capitalize">{{ item.status }}</dd>@if (item.issue_date) { <dt class="text-content-muted">Issue date</dt><dd>{{ item.issue_date | date:'dd MMM yyyy' }}</dd> }@if (item.received_on) { <dt class="text-content-muted">Received on</dt><dd>{{ item.received_on | date:'dd MMM yyyy' }}</dd> }</dl> }
    @else { <div class="mx-auto mt-7 grid place-items-center rounded-full bg-danger/10 text-danger w-16 h-16"><mat-icon class="material-icons-outlined text-4xl">gpp_bad</mat-icon></div><h1 class="text-2xl font-bold mt-4">Document not verified</h1><p class="text-content-muted mt-2">No billing record matches this verification code. Check the code or contact the issuing firm.</p> }
  </section></main>` })
export class InvoiceVerificationComponent {
  private readonly route = inject(ActivatedRoute); private readonly billing = inject(BillingService);
  protected readonly result = signal<BillingVerification | null>(null); protected readonly loading = signal(true);
  constructor() { this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => { const code = p.get('code') || ''; void this.verify(code); }); }
  private async verify(code: string): Promise<void> { this.loading.set(true); try { this.result.set(await firstValueFrom(this.billing.verifyDocument(code))); } catch { this.result.set(null); } finally { this.loading.set(false); } }
  protected money(value: string | number): string { return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`; }
  protected label(type: string): string { return type.replaceAll('_', ' '); }
}

import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ClientsService } from '@core/services/clients.service';
import { ClientFields, FIELD_LABELS, KycPublicView, KycSubmitResult } from '@core/models/clients.models';
import { ClientFormComponent } from './client-form.component';

/**
 * The client's KYC form, reached from the tokenised link (no login).
 * Prefilled with what the firm holds; the client corrects, consents,
 * declares, and submits. Validation findings are shown but do not block.
 */
@Component({
  selector: 'app-kyc-form',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, MatIconModule, MatButtonModule, ClientFormComponent],
  templateUrl: './kyc-form.component.html',
})
export class KycFormComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly clients = inject(ClientsService);

  protected readonly view = signal<KycPublicView | null>(null);
  protected readonly loading = signal(true);
  protected readonly invalid = signal(false);
  protected readonly submitting = signal(false);
  protected readonly result = signal<KycSubmitResult | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly fieldLabels = FIELD_LABELS;
  protected declaration = false;
  private token = '';
  private values: ClientFields = {};

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => {
      this.token = p.get('token') ?? '';
      void this.load();
    });
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      const v = await firstValueFrom(this.clients.kycView(this.token));
      this.view.set(v);
      this.values = { ...v.prefill };
    } catch {
      this.invalid.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  protected onChange(v: ClientFields): void { this.values = v; }

  protected async submit(): Promise<void> {
    if (!this.declaration) { this.error.set('Please confirm the declaration before submitting.'); return; }
    this.error.set(null);
    this.submitting.set(true);
    try {
      this.result.set(await firstValueFrom(this.clients.kycSubmit(this.token, {
        ...this.values,
        consent_email: !!this.values.consent_email,
        consent_mobile: !!this.values.consent_mobile,
        consent_whatsapp: !!this.values.consent_whatsapp,
        declaration_accepted: true,
      })));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      const detail = err instanceof HttpErrorResponse ? (err.error?.detail as string | undefined) : undefined;
      this.error.set(detail || 'Could not submit the form. Please try again.');
    } finally {
      this.submitting.set(false);
    }
  }

  protected label(field: string): string { return FIELD_LABELS[field] ?? field; }
}

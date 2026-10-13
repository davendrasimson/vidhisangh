import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ClientsService } from '@core/services/clients.service';
import { MattersService } from '@core/services/matters.service';
import { DocumentsService } from '@core/services/documents.service';
import { BillingService } from '@core/services/billing.service';
import { DocFile } from '@core/models/documents.models';
import { Invoice } from '@core/models/billing.models';
import { NotificationService } from '@core/services/notification.service';
import { Matter } from '@core/models/matters.models';
import {
  Client,
  ClientFields,
  FIELD_LABELS,
  KycRequest,
  KycRequestDetail,
  ReferenceData,
} from '@core/models/clients.models';
import { ClientFormComponent } from './client-form.component';
import { ClientPrivacyService, saveBlob } from './client-privacy.service';
import { CONSENT_PURPOSE_LABELS, ClientFormFields, ConsentEvent, ConsentPurpose, LegalHold } from './client-privacy.models';
import { AuthService } from '@core/auth/auth.service';

/** One client: details (editable), tax defaults, and the KYC form workflow. */
@Component({
  selector: 'app-client-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, ClientFormComponent],
  templateUrl: './client-detail.component.html',
})
export class ClientDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly clients = inject(ClientsService);
  private readonly mattersApi = inject(MattersService);
  private readonly notify = inject(NotificationService);
  private readonly documentsApi = inject(DocumentsService);
  private readonly billingApi = inject(BillingService);
  private readonly privacy = inject(ClientPrivacyService);
  private readonly auth = inject(AuthService);

  protected readonly client = signal<Client | null>(null);
  /** Matters filed for this client (linked through the client master). */
  protected readonly matters = signal<Matter[]>([]);
  protected readonly documents = signal<DocFile[]>([]);
  protected readonly invoices = signal<Invoice[]>([]);
  protected readonly outstanding = computed(() => this.invoices().reduce((sum, i) => sum + Math.max(0, Number(i.total) - Number(i.amount_paid)), 0));
  protected readonly reference = signal<ReferenceData | null>(null);
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly dirty = signal(false);
  protected readonly requests = signal<KycRequest[]>([]);
  protected readonly review = signal<KycRequestDetail | null>(null);
  protected readonly showSend = signal(false);
  protected readonly fieldLabels = FIELD_LABELS;
  protected sendForm = { send_to_email: '', message: '', expires_in_days: 14 };
  private edits: ClientFormFields = {};
  /** Consent ledger (newest first) and the staff "record consent" mini-form. */
  protected readonly consents = signal<ConsentEvent[]>([]);
  protected readonly showConsents = signal(false);
  protected readonly purposeLabels = CONSENT_PURPOSE_LABELS;
  protected readonly purposes = Object.keys(CONSENT_PURPOSE_LABELS) as ConsentPurpose[];
  protected consentForm: { purpose: ConsentPurpose; granted: boolean; note: string } = { purpose: 'contact_email', granted: true, note: '' };
  protected readonly canOverrideHold = this.auth.hasPermission('tenant:manage');

  protected readonly errors = computed(() => this.client()?.issues.filter((i) => i.severity === 'error') ?? []);
  protected readonly warnings = computed(() => this.client()?.issues.filter((i) => i.severity === 'warning') ?? []);
  protected readonly openRequest = computed(() => this.requests().find((r) => r.status === 'sent') ?? null);
  protected readonly submittedRequest = computed(() => this.requests().find((r) => r.status === 'submitted') ?? null);

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => {
      const id = p.get('id');
      if (id) void this.load(id);
    });
  }

  private async load(id: string): Promise<void> {
    this.loading.set(true);
    try {
      const [client, reference, requests] = await Promise.all([
        firstValueFrom(this.clients.get(id)),
        this.reference() ? Promise.resolve(this.reference()!) : firstValueFrom(this.clients.reference()),
        firstValueFrom(this.clients.kycRequests(id)),
      ]);
      this.client.set(client);
      this.reference.set(reference);
      this.requests.set(requests);
      this.sendForm.send_to_email = client.email || client.contact_person_email || '';
      firstValueFrom(this.privacy.consents(id)).then((x) => this.consents.set(x)).catch(() => this.consents.set([]));
      // Matters for this client — non-fatal if the user cannot read matters.
      firstValueFrom(this.mattersApi.list(undefined, 1, 50, { client_id: id }))
        .then((m) => this.matters.set(m))
        .catch(() => this.matters.set([]));
      firstValueFrom(this.documentsApi.list({ clientId: id })).then((x) => this.documents.set(x)).catch(() => this.documents.set([]));
      firstValueFrom(this.billingApi.list(undefined, { clientId: id })).then((x) => this.invoices.set(x)).catch(() => this.invoices.set([]));
      // Deep link from the notification: /app/clients/:id?kyc=<request id>
      const kyc = this.route.snapshot.queryParamMap.get('kyc');
      const target = kyc ?? requests.find((r) => r.status === 'submitted')?.id;
      if (target) await this.openReview(target);
    } catch {
      await this.router.navigate(['/app/clients']);
    } finally {
      this.loading.set(false);
    }
  }

  // ── Details ────────────────────────────────────────────────────
  protected onChange(v: ClientFormFields): void {
    this.edits = v;
    this.dirty.set(true);
  }

  protected async save(): Promise<void> {
    const c = this.client();
    if (!c) return;
    this.saving.set(true);
    try {
      const updated = await firstValueFrom(this.clients.update(c.id, this.edits));
      this.client.set(updated);
      this.dirty.set(false);
      this.notify.success(updated.issues.some((i) => i.severity === 'error')
        ? 'Saved — some details need attention (see the notes above).' : 'Client saved.');
    } catch { /* handled */ } finally { this.saving.set(false); }
  }

  protected async remove(): Promise<void> {
    const c = this.client();
    if (!c || !window.confirm(`Delete ${c.display_name}? The record is kept (recoverable) for the retention period; matters and invoices keep their own copies of the name.`)) return;
    try {
      await firstValueFrom(this.clients.remove(c.id));
      await this.router.navigate(['/app/clients']);
    } catch { /* handled */ }
  }

  // ── Privacy: export, consent ledger, erasure ───────────────────
  protected async exportData(): Promise<void> {
    const c = this.client();
    if (!c) return;
    try {
      await saveBlob(await firstValueFrom(this.privacy.exportBlob(c.id)), `client-${c.display_name.replace(/[^\w-]+/g, '_')}.json`);
      this.notify.success('Client data export downloaded (DPDP s.11).');
    } catch { /* handled */ }
  }

  protected async recordConsent(): Promise<void> {
    const c = this.client();
    if (!c) return;
    this.saving.set(true);
    try {
      const ev = await firstValueFrom(this.privacy.recordConsent(c.id, this.consentForm.purpose, this.consentForm.granted, this.consentForm.note.trim() || undefined));
      this.consents.update((list) => [ev, ...list]);
      this.client.set(await firstValueFrom(this.clients.get(c.id)));
      this.consentForm.note = '';
      this.notify.success(this.consentForm.granted ? 'Consent recorded.' : 'Withdrawal recorded — the original grant stays on file.');
    } catch { /* handled */ } finally { this.saving.set(false); }
  }

  protected async erase(): Promise<void> {
    const c = this.client();
    if (!c) return;
    let holds: LegalHold[] = [];
    try { holds = await firstValueFrom(this.privacy.legalHolds(c.id)); } catch { /* handled */ }
    let overrideLegalHold = false;
    let reason: string | undefined;
    if (holds.length) {
      const list = holds.map((h) => `${h.matter_number} — ${h.reason}`).join('\n');
      if (!this.canOverrideHold) {
        window.alert(`This client is under legal hold and cannot be erased:\n\n${list}\n\nClose the matters or ask an organisation administrator.`);
        return;
      }
      reason = window.prompt(`Legal hold on:\n\n${list}\n\nTo override, enter the reason (recorded in the audit log):`)?.trim();
      if (!reason) return;
      overrideLegalHold = true;
    }
    if (!window.confirm(`Permanently erase ${c.display_name}? Identity data, KYC forms and consent records are deleted; matters, documents and invoices are kept but unlinked and shown as “Erased client”. This cannot be undone.`)) return;
    this.saving.set(true);
    try {
      const res = await firstValueFrom(this.privacy.erase(c.id, { overrideLegalHold, reason }));
      const n = Object.values(res.unlinked).reduce((a, b) => a + b, 0);
      this.notify.success(`Client erased. ${n} linked record${n === 1 ? '' : 's'} unlinked.`);
      await this.router.navigate(['/app/clients']);
    } catch (err) {
      const detail = (err as { error?: { detail?: string } })?.error?.detail;
      if (detail) this.notify.error(detail);
    } finally { this.saving.set(false); }
  }

  protected sourceLabel(s: ConsentEvent['source']): string {
    return { staff: 'by staff', kyc_form: 'by the client (KYC form)', portal: 'by the client (portal)' }[s];
  }

  // ── KYC ────────────────────────────────────────────────────────
  protected async sendKyc(): Promise<void> {
    const c = this.client();
    if (!c) return;
    this.saving.set(true);
    try {
      const req = await firstValueFrom(this.clients.sendKyc(c.id, {
        send_to_email: this.sendForm.send_to_email.trim() || null,
        message: this.sendForm.message.trim() || null,
        expires_in_days: this.sendForm.expires_in_days,
      }));
      this.requests.set([req, ...this.requests().filter((r) => r.id !== req.id).map((r) => r.status === 'sent' ? { ...r, status: 'cancelled' as const, url: null } : r)]);
      this.client.update((cur) => (cur ? { ...cur, kyc_status: 'pending' } : cur));
      this.showSend.set(false);
      this.notify.success(req.sent_to_email ? `KYC form sent to ${req.sent_to_email}. The link is also below to share.` : 'KYC link created — copy it below to share.');
    } catch { /* handled */ } finally { this.saving.set(false); }
  }

  protected async copyLink(url: string): Promise<void> {
    try { await navigator.clipboard.writeText(url); this.notify.success('Link copied.'); }
    catch { window.prompt('Copy this link', url); }
  }

  protected async cancelKyc(r: KycRequest): Promise<void> {
    const c = this.client();
    if (!c || !window.confirm('Withdraw this KYC link? The client will no longer be able to use it.')) return;
    try {
      const updated = await firstValueFrom(this.clients.cancelKyc(c.id, r.id));
      this.requests.update((list) => list.map((x) => (x.id === updated.id ? updated : x)));
      if (this.review()?.id === r.id) this.review.set(null);
    } catch { /* handled */ }
  }

  protected async openReview(requestId: string): Promise<void> {
    const c = this.client();
    if (!c) return;
    try { this.review.set(await firstValueFrom(this.clients.kycRequest(c.id, requestId))); }
    catch { /* handled */ }
  }

  protected async apply(): Promise<void> {
    const c = this.client();
    const r = this.review();
    if (!c || !r) return;
    this.saving.set(true);
    try {
      const updated = await firstValueFrom(this.clients.applyKyc(c.id, r.id));
      this.client.set(updated);
      this.requests.set(await firstValueFrom(this.clients.kycRequests(c.id)));
      this.review.set(null);
      this.dirty.set(false);
      this.notify.success('KYC applied — client details updated and marked verified.');
    } catch { /* handled */ } finally { this.saving.set(false); }
  }

  protected contactChannels(c: Client): string {
    const on = [c.consent_email && 'Email', c.consent_mobile && 'SMS / calls', c.consent_whatsapp && 'WhatsApp'].filter(Boolean);
    return on.join(' · ') || '— no consent recorded';
  }
  protected label(field: string): string { return FIELD_LABELS[field] ?? field; }
  protected show(v: unknown): string {
    if (v === null || v === undefined || v === '') return '—';
    if (typeof v === 'boolean') return v ? 'Yes' : 'No';
    return String(v);
  }
  protected statusLabel(s: KycRequest['status']): string {
    return { sent: 'Sent — awaiting the client', submitted: 'Submitted — review', applied: 'Applied', expired: 'Expired', cancelled: 'Withdrawn' }[s];
  }
}

import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { firstValueFrom } from 'rxjs';
import { BillingBranding } from '@core/models/billing.models';
import { BillingService } from '@core/services/billing.service';
import { NotificationService } from '@core/services/notification.service';

const DEFAULTS: BillingBranding = {
  template_id: 'classic', legal_name: '', address: '', email: '', phone: '', gstin: '', pan: '',
  logo_url: '', accent_color: '#215dcc', bank_details: '',
  payment_terms: 'Payment due within 15 days.', footer: 'This is a system-generated document.',
  signature_name: '', proforma_prefix: 'PF', invoice_prefix: 'INV',
  credit_note_prefix: 'CN', receipt_prefix: 'RCT',
};

@Component({
  selector: 'app-billing-branding',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatButtonModule, MatIconModule],
  template: `
    <div class="mx-auto w-full">
      <header class="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div><h1 class="text-2xl font-bold text-content">Billing documents &amp; branding</h1>
          <p class="text-content-muted mt-1">Set the appearance and numbering of proforma invoices, tax invoices, credit notes and receipts.</p></div>
        <button mat-flat-button color="primary" [disabled]="saving()" (click)="save()">
          <mat-icon class="material-icons-outlined">save</mat-icon>{{ saving() ? 'Saving…' : 'Save branding' }}
        </button>
      </header>

      <section class="rounded-card border border-line bg-surface-raised shadow-card p-5 mb-5">
        <h2 class="font-semibold text-content">Choose a document template</h2>
        <div class="grid md:grid-cols-3 gap-4 mt-4">
          @for (template of templates; track template.id) {
            <button class="template-card" [class.selected]="form.template_id === template.id" (click)="form.template_id = template.id">
              <span class="template-sheet" [class]="'template-sheet ' + template.id" [style.--preview-accent]="form.accent_color">
                <i></i><b></b><em></em><span></span>
              </span>
              <strong>{{ template.name }}</strong><small>{{ template.description }}</small>
            </button>
          }
        </div>
      </section>

      <div class="grid xl:grid-cols-[1.25fr_.75fr] gap-5">
        <section class="rounded-card border border-line bg-surface-raised shadow-card p-5">
          <h2 class="font-semibold text-content">Firm identity</h2>
          <div class="grid sm:grid-cols-2 gap-3 mt-4">
            <label class="grid gap-1 sm:col-span-2"><span>Legal / firm name</span><input class="vs-input" [(ngModel)]="form.legal_name" /></label>
            <label class="grid gap-1 sm:col-span-2"><span>Office address</span><textarea class="vs-input min-h-20" [(ngModel)]="form.address"></textarea></label>
            <label class="grid gap-1"><span>Billing email</span><input class="vs-input" type="email" [(ngModel)]="form.email" /></label>
            <label class="grid gap-1"><span>Phone</span><input class="vs-input" [(ngModel)]="form.phone" /></label>
            <label class="grid gap-1"><span>GSTIN</span><input class="vs-input uppercase" [(ngModel)]="form.gstin" /></label>
            <label class="grid gap-1"><span>PAN</span><input class="vs-input uppercase" [(ngModel)]="form.pan" /></label>
            <label class="grid gap-1 sm:col-span-2"><span>Logo URL (HTTPS)</span><input class="vs-input" type="url" [(ngModel)]="form.logo_url" placeholder="https://…/logo.png" /></label>
            <label class="grid gap-1"><span>Accent colour</span><input class="h-10 w-full rounded-lg border border-line" type="color" [(ngModel)]="form.accent_color" /></label>
            <label class="grid gap-1"><span>Authorised signatory</span><input class="vs-input" [(ngModel)]="form.signature_name" /></label>
            <label class="grid gap-1 sm:col-span-2"><span>Bank / UPI payment details</span><textarea class="vs-input min-h-24" [(ngModel)]="form.bank_details"></textarea></label>
            <label class="grid gap-1 sm:col-span-2"><span>Payment terms</span><textarea class="vs-input min-h-20" [(ngModel)]="form.payment_terms"></textarea></label>
            <label class="grid gap-1 sm:col-span-2"><span>Document footer</span><textarea class="vs-input min-h-20" [(ngModel)]="form.footer"></textarea></label>
          </div>
        </section>

        <section class="rounded-card border border-line bg-surface-raised shadow-card p-5 self-start">
          <h2 class="font-semibold text-content">Numbering prefixes</h2>
          <p class="text-sm text-content-muted mt-1">The sequence number is added automatically.</p>
          <div class="grid gap-3 mt-4">
            <label class="grid gap-1"><span>Proforma invoice</span><input class="vs-input uppercase" [(ngModel)]="form.proforma_prefix" /></label>
            <label class="grid gap-1"><span>Tax invoice</span><input class="vs-input uppercase" [(ngModel)]="form.invoice_prefix" /></label>
            <label class="grid gap-1"><span>Credit note</span><input class="vs-input uppercase" [(ngModel)]="form.credit_note_prefix" /></label>
            <label class="grid gap-1"><span>Receipt</span><input class="vs-input uppercase" [(ngModel)]="form.receipt_prefix" /></label>
          </div>
          <div class="rounded-lg bg-surface-sunken border border-line p-4 mt-5 text-sm">
            <p class="font-medium text-content">Example numbers</p>
            <p class="text-content-muted mt-2 font-mono">{{ form.proforma_prefix || 'PF' }}-0001</p>
            <p class="text-content-muted font-mono">{{ form.invoice_prefix || 'INV' }}-0001</p>
            <p class="text-content-muted font-mono">{{ form.credit_note_prefix || 'CN' }}-0001</p>
            <p class="text-content-muted font-mono">{{ form.receipt_prefix || 'RCT' }}-0001</p>
          </div>
        </section>
      </div>
    </div>
  `,
  styles: [`
    label span { color: rgb(var(--vs-text-muted)); font-size: .78rem; }
    .template-card { display:grid; gap:.5rem; padding:.8rem; border:1px solid rgb(var(--vs-border)); border-radius:12px; text-align:left; }
    .template-card:hover,.template-card.selected { border-color:rgb(var(--vs-brand)); background:color-mix(in srgb,rgb(var(--vs-brand)) 5%,transparent); }
    .template-card small { color:rgb(var(--vs-text-muted)); }
    .template-sheet { position:relative; display:block; height:105px; padding:13px; border-radius:6px; background:#fff; box-shadow:0 4px 15px rgb(15 23 42/.12); }
    .template-sheet i,.template-sheet b,.template-sheet em,.template-sheet span { display:block; height:5px; margin-bottom:7px; border-radius:2px; background:#dbe3ef; }
    .template-sheet i { width:38%; height:10px; background:var(--preview-accent); }.template-sheet b{width:70%}.template-sheet em{width:52%}.template-sheet span{width:88%;margin-top:18px}
    .template-sheet.modern { border-top:8px solid var(--preview-accent); }.template-sheet.minimal i{background:#1e293b}.template-sheet.classic{border:1px solid #cbd5e1}
  `],
})
export class BillingBrandingComponent implements OnInit {
  private readonly billing = inject(BillingService);
  private readonly notify = inject(NotificationService);
  protected readonly saving = signal(false);
  protected form: BillingBranding = { ...DEFAULTS };
  protected readonly templates = [
    { id: 'classic' as const, name: 'Classic chambers', description: 'Formal bordered layout for litigation practices.' },
    { id: 'modern' as const, name: 'Modern firm', description: 'Strong colour band and clear commercial hierarchy.' },
    { id: 'minimal' as const, name: 'Minimal counsel', description: 'Clean typography for individual advocates.' },
  ];

  async ngOnInit(): Promise<void> {
    try { this.form = await firstValueFrom(this.billing.branding()); } catch { /* handled */ }
  }

  protected async save(): Promise<void> {
    if (this.saving()) return;
    this.saving.set(true);
    try {
      this.form = await firstValueFrom(this.billing.saveBranding(this.form));
      this.notify.success('Billing branding saved.');
    } catch { /* handled */ } finally { this.saving.set(false); }
  }
}

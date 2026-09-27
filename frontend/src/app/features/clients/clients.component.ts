import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ClientsService } from '@core/services/clients.service';
import { NotificationService } from '@core/services/notification.service';
import { ClientFields, ClientKind, ClientStatus, ClientSummary, ReferenceData } from '@core/models/clients.models';
import { ClientFormComponent } from './client-form.component';

/** Client master: the list, filters, and a "new client" panel. */
@Component({
  selector: 'app-clients',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, ClientFormComponent],
  templateUrl: './clients.component.html',
})
export class ClientsComponent implements OnInit {
  private readonly clients = inject(ClientsService);
  private readonly notify = inject(NotificationService);
  private readonly router = inject(Router);

  protected readonly items = signal<ClientSummary[]>([]);
  protected readonly loading = signal(true);
  protected readonly reference = signal<ReferenceData | null>(null);
  protected readonly showNew = signal(false);
  protected readonly saving = signal(false);
  protected q = '';
  protected kind: ClientKind | '' = '';
  protected status: ClientStatus | '' = 'active';
  protected newKind: ClientKind = 'individual';
  protected newValues: ClientFields = {};

  async ngOnInit(): Promise<void> {
    try { this.reference.set(await firstValueFrom(this.clients.reference())); } catch { /* handled */ }
    await this.load();
  }

  protected async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.items.set(await firstValueFrom(this.clients.list({ q: this.q.trim(), kind: this.kind, status: this.status })));
    } catch { /* handled */ } finally { this.loading.set(false); }
  }

  protected startNew(kind: ClientKind): void {
    this.newKind = kind;
    this.newValues = {};
    this.showNew.set(true);
  }

  protected onNewChange(v: ClientFields): void { this.newValues = v; }

  protected async create(): Promise<void> {
    const v = this.newValues;
    const name = this.newKind === 'business'
      ? (v.legal_name || v.trade_name || '').trim()
      : [v.first_name, v.last_name].filter(Boolean).join(' ').trim();
    if (!name) { this.notify.error(this.newKind === 'business' ? 'Enter the business name.' : 'Enter the client\'s name.'); return; }
    this.saving.set(true);
    try {
      const created = await firstValueFrom(this.clients.create({ ...v, kind: this.newKind, display_name: name }));
      this.notify.success(`${created.display_name} added.`);
      this.showNew.set(false);
      await this.router.navigate(['/app/clients', created.id]);
    } catch { /* handled */ } finally { this.saving.set(false); }
  }

  protected kycLabel(s: ClientSummary['kyc_status']): string {
    return { not_started: 'KYC not started', pending: 'KYC sent', submitted: 'KYC to review', verified: 'KYC verified' }[s];
  }
}

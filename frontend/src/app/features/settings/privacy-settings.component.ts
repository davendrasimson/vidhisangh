import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { environment } from '@env/environment';
import { AuthService } from '@core/auth/auth.service';
import { NotificationService } from '@core/services/notification.service';
import { saveBlob } from '@features/clients/client-privacy.service';
import { PrivacyNoticeFacts } from '@features/legal/legal-page.component';

interface TenantPrivacySettings {
  data_protection_contact_name: string | null;
  data_protection_contact_email: string | null;
  data_protection_contact_phone: string | null;
  matter_retention_years: number;
  directory_listing_default: boolean;
  dpa_version: string;
  processor_name: string;
  sub_processors: string[];
}

/**
 * Settings → Privacy & data. Your rights as a user (export, erase, directory
 * opt-out) and, for tenant admins, the organisation's privacy settings,
 * full export and offboarding (DPDP s.11–s.13).
 */
@Component({
  selector: 'app-privacy-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatButtonModule, MatIconModule, MatSlideToggleModule],
  templateUrl: './privacy-settings.component.html',
})
export class PrivacySettingsComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly notify = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly api = environment.apiBaseUrl;

  protected readonly facts = signal<PrivacyNoticeFacts | null>(null);
  protected readonly busy = signal<string | null>(null);
  protected readonly discoverable = signal<boolean | null>(null);
  protected readonly isAdmin = this.auth.hasPermission('tenant:manage');
  protected readonly tenantSettings = signal<TenantPrivacySettings | null>(null);
  protected readonly tenantSlug = signal<string>('');

  protected showDelete = false;
  protected deletePassword = '';
  protected showOrgDelete = false;
  protected orgConfirmSlug = '';
  protected orgPassword = '';
  protected orgForm = { data_protection_contact_name: '', data_protection_contact_email: '', data_protection_contact_phone: '', matter_retention_years: 8 };

  async ngOnInit(): Promise<void> {
    try { this.facts.set(await firstValueFrom(this.http.get<PrivacyNoticeFacts>(`${this.api}/privacy/notice`))); } catch { /* shown without facts */ }
    try {
      const v = await firstValueFrom(this.http.get<{ discoverable: boolean }>(`${this.api}/network/me/visibility`));
      this.discoverable.set(v.discoverable);
    } catch { this.discoverable.set(true); }
    if (this.isAdmin) {
      try {
        const [s, t] = await Promise.all([
          firstValueFrom(this.http.get<TenantPrivacySettings>(`${this.api}/tenants/current/privacy`)),
          firstValueFrom(this.http.get<{ slug: string }>(`${this.api}/tenants/current`)),
        ]);
        this.tenantSettings.set(s);
        this.tenantSlug.set(t.slug);
        this.orgForm = {
          data_protection_contact_name: s.data_protection_contact_name ?? '',
          data_protection_contact_email: s.data_protection_contact_email ?? '',
          data_protection_contact_phone: s.data_protection_contact_phone ?? '',
          matter_retention_years: s.matter_retention_years,
        };
      } catch { /* handled by interceptor */ }
    }
  }

  // ── My data ──────────────────────────────────────────────────────
  protected async exportMe(): Promise<void> {
    this.busy.set('export');
    try {
      const blob = await firstValueFrom(this.http.get(`${this.api}/privacy/me/export`, { responseType: 'blob' }));
      await saveBlob(blob, `vidhisangh-my-data-${new Date().toISOString().slice(0, 10)}.json`);
      this.notify.success('Your data export has been downloaded.');
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  protected async toggleDirectory(on: boolean): Promise<void> {
    this.busy.set('directory');
    try {
      await firstValueFrom(this.http.patch(`${this.api}/network/me/visibility`, { discoverable: on }));
      this.discoverable.set(on);
      this.notify.success(on ? 'You are listed in the directory.' : 'You have been removed from the directory.');
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  protected async deleteMe(): Promise<void> {
    if (!this.deletePassword) { this.notify.error('Enter your password to confirm.'); return; }
    if (!window.confirm('Delete your account? This anonymises your account immediately and signs you out everywhere. It cannot be undone.')) return;
    this.busy.set('delete');
    try {
      await firstValueFrom(this.http.post(`${this.api}/privacy/me/delete`, { password: this.deletePassword }));
      this.notify.success('Your account has been deleted.');
      await this.auth.logout();
      await this.router.navigate(['/auth/login']);
    } catch (err) {
      const detail = err instanceof HttpErrorResponse ? (err.error?.detail as string | undefined) : undefined;
      if (detail) this.notify.error(detail);
    } finally { this.busy.set(null); }
  }

  // ── Organisation (tenant:manage) ─────────────────────────────────
  protected async saveOrg(): Promise<void> {
    this.busy.set('org');
    try {
      const s = await firstValueFrom(this.http.patch<TenantPrivacySettings>(`${this.api}/tenants/current/privacy`, {
        data_protection_contact_name: this.orgForm.data_protection_contact_name || null,
        data_protection_contact_email: this.orgForm.data_protection_contact_email || null,
        data_protection_contact_phone: this.orgForm.data_protection_contact_phone || null,
        matter_retention_years: Number(this.orgForm.matter_retention_years) || 8,
      }));
      this.tenantSettings.set(s);
      this.notify.success('Organisation privacy settings saved.');
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  protected async exportOrg(): Promise<void> {
    this.busy.set('org-export');
    try {
      const blob = await firstValueFrom(this.http.post(`${this.api}/tenants/current/export`, {}, { responseType: 'blob' }));
      await saveBlob(blob, `${this.tenantSlug() || 'organisation'}-export.zip`);
      this.notify.success('Organisation export downloaded (zip of per-table JSON).');
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  protected async deleteOrg(): Promise<void> {
    if (this.orgConfirmSlug.trim() !== this.tenantSlug()) { this.notify.error(`Type the organisation slug "${this.tenantSlug()}" to confirm.`); return; }
    if (!this.orgPassword) { this.notify.error('Enter your password to confirm.'); return; }
    if (!window.confirm(`Cancel the organisation "${this.tenantSlug()}"? Every user is disabled now and all data is erased after ${this.facts()?.tenant_erase_grace_days ?? 30} days.`)) return;
    this.busy.set('org-delete');
    try {
      await firstValueFrom(this.http.request('DELETE', `${this.api}/tenants/current`, { body: { confirm_slug: this.orgConfirmSlug.trim(), password: this.orgPassword } }));
      this.notify.success('Organisation cancelled. Erasure is scheduled after the grace period.');
      await this.auth.logout();
      await this.router.navigate(['/auth/login']);
    } catch (err) {
      const detail = err instanceof HttpErrorResponse ? (err.error?.detail as string | undefined) : undefined;
      if (detail) this.notify.error(detail);
    } finally { this.busy.set(null); }
  }
}

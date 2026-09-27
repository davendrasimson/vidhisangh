import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '@core/auth/auth.service';

interface SettingsTile {
  label: string;
  icon: string;
  description: string;
  route: string;
  permission?: string;
}

interface SettingsSection {
  title: string;
  tiles: SettingsTile[];
}

/** Settings hub: every settings/admin area as a card ("ticket"). Replaces the
 *  old collapsible sub-menu in the sidebar. Tiles are permission-gated. */
@Component({
  selector: 'app-settings-home',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    <div class="w-full">
      <header class="mb-6">
        <h1 class="text-2xl font-bold text-content">Settings</h1>
        <p class="text-content-muted mt-1">Manage your organisation, integrations and account.</p>
      </header>

      @for (section of visibleSections(); track section.title) {
        <section class="mb-8">
          <h2 class="text-xs font-bold uppercase tracking-wider text-content-muted mb-3">
            {{ section.title }}
          </h2>
          <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            @for (tile of section.tiles; track tile.route) {
              <a
                [routerLink]="tile.route"
                class="vs-settings-tile rounded-card bg-surface-raised border border-line shadow-card p-5 transition hover:border-brand/60"
              >
                <span class="vs-settings-tile__icon">
                  <mat-icon class="material-icons-outlined">{{ tile.icon }}</mat-icon>
                </span>
                <h3 class="font-semibold text-content mt-3">{{ tile.label }}</h3>
                <p class="text-sm text-content-muted mt-1">{{ tile.description }}</p>
                <span class="vs-settings-tile__go">
                  Open <mat-icon class="material-icons-outlined">arrow_forward</mat-icon>
                </span>
              </a>
            }
          </div>
        </section>
      }
    </div>
  `,
  styles: [
    `
      .vs-settings-tile {
        display: block;
        text-decoration: none;
        color: inherit;
      }
      .vs-settings-tile__icon {
        display: inline-grid;
        place-items: center;
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: color-mix(in srgb, rgb(var(--vs-brand)) 12%, transparent);
        color: rgb(var(--vs-brand));
      }
      .vs-settings-tile__icon mat-icon {
        font-size: 24px;
        width: 24px;
        height: 24px;
      }
      .vs-settings-tile__go {
        display: inline-flex;
        align-items: center;
        gap: 2px;
        margin-top: 0.9rem;
        font-size: 0.82rem;
        font-weight: 600;
        color: rgb(var(--vs-brand));
        opacity: 0;
        transition: opacity 0.15s ease;
      }
      .vs-settings-tile__go mat-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
      }
      .vs-settings-tile:hover .vs-settings-tile__go {
        opacity: 1;
      }
    `,
  ],
})
export class SettingsHomeComponent {
  private readonly auth = inject(AuthService);

  private readonly sections: SettingsSection[] = [
    {
      title: 'Organisation',
      tiles: [
        { label: 'Users', icon: 'manage_accounts', description: 'Invite users, assign roles, activate or deactivate.', route: '/app/admin/users', permission: 'user:read' },
        { label: 'Counsel Rates', icon: 'request_quote', description: 'Standard charges per person: hourly, per hearing, per day, per matter, retainer.', route: '/app/settings/counsel-rates', permission: 'matter:read' },
        { label: 'Feature Flags', icon: 'toggle_on', description: 'Turn platform capabilities on or off per tenant.', route: '/app/admin/feature-flags', permission: 'tenant:manage' },
        { label: 'Subscription', icon: 'workspace_premium', description: 'Your plan, live usage and limits.', route: '/app/admin/subscription', permission: 'tenant:manage' },
        { label: 'Audit Log', icon: 'history', description: 'Immutable log of security and config changes.', route: '/app/admin/audit', permission: 'audit:read' },
        { label: 'System', icon: 'monitor_heart', description: 'Health checks and configuration status.', route: '/app/admin/system', permission: 'tenant:manage' },
      ],
    },
    {
      title: 'Integrations',
      tiles: [
        { label: 'Webhooks', icon: 'webhook', description: 'Outbound event endpoints and delivery log.', route: '/app/admin/webhooks', permission: 'webhook:manage' },
        { label: 'API Keys', icon: 'vpn_key', description: 'Scoped tokens for programmatic access.', route: '/app/admin/api-keys', permission: 'apikey:manage' },
      ],
    },
    {
      title: 'Your account',
      tiles: [
        { label: 'Appearance', icon: 'palette', description: 'Theme (light / dark) and accent colour.', route: '/app/settings/appearance' },
        { label: 'Account Security', icon: 'fingerprint', description: 'Passkeys, active sessions and MFA.', route: '/app/settings/security' },
        { label: 'Notifications', icon: 'notifications', description: 'Channels and per-type delivery preferences.', route: '/app/settings/notifications' },
      ],
    },
  ];

  protected readonly visibleSections = computed(() =>
    this.sections
      .map((s) => ({
        ...s,
        tiles: s.tiles.filter((t) => !t.permission || this.auth.hasPermission(t.permission)),
      }))
      .filter((s) => s.tiles.length > 0),
  );
}

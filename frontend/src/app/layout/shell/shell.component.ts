import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { BreakpointObserver } from '@angular/cdk/layout';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AuthService } from '@core/auth/auth.service';
import { ThemeService } from '@core/services/theme.service';
import { RealtimeService } from '@core/services/realtime.service';
import { NotificationsBellComponent } from './notifications-bell.component';
import { TermsUpdatePromptComponent } from './terms-update-prompt.component';
import { SupportDialogComponent } from './support-dialog.component';

interface NavItem {
  label: string;
  icon: string;
  route: string;
  permission?: string;
  queryParams?: Record<string, string>;
}

interface NavGroup {
  /** Optional section heading; omitted for the top-level (un-headed) group. */
  title?: string;
  /** Shown when the group is collapsible (acts as the toggle's leading icon). */
  icon?: string;
  items: NavItem[];
  /** When true, the group renders as a single expandable entry (e.g. Settings). */
  collapsible?: boolean;
}

/** Authenticated application shell: responsive sidenav + top bar. */
@Component({
  selector: 'app-shell',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterOutlet, RouterLink, RouterLinkActive,
    MatSidenavModule, MatToolbarModule, MatListModule, MatIconModule,
    MatButtonModule, MatMenuModule, MatTooltipModule, NotificationsBellComponent,
    TermsUpdatePromptComponent, SupportDialogComponent,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  protected readonly auth = inject(AuthService);
  protected readonly theme = inject(ThemeService);
  private readonly realtime = inject(RealtimeService);
  protected readonly opened = signal(true);
  protected readonly compact = signal(false);

  constructor() {
    inject(BreakpointObserver).observe('(max-width: 767px)').pipe(takeUntilDestroyed()).subscribe(({ matches }) => {
      this.compact.set(matches);
      this.opened.set(!matches);
    });
  }

  protected closeMobileNavigation(): void {
    if (this.compact()) this.opened.set(false);
  }

  ngOnInit(): void {
    // Live messaging socket is app-wide so delivery/presence work everywhere.
    this.realtime.connect();
  }

  protected readonly user = this.auth.user;
  protected readonly initials = computed(() => {
    const name = this.user()?.full_name ?? '';
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || 'U';
  });

  // Day-to-day workspace grouped by area; one-time-setup / admin / integration
  // items live in the collapsible "Settings" group so the rail stays short.
  // Personal account items (profile, security, notifications) live in the
  // top-right account menu, not here.
  protected readonly navGroups: NavGroup[] = [
    {
      items: [{ label: 'Dashboard', icon: 'dashboard', route: '/app/dashboard' }],
    },
    {
      title: 'Network',
      items: [
        { label: 'Feed', icon: 'dynamic_feed', route: '/app/network' },
        { label: 'People', icon: 'groups', route: '/app/people' },
        { label: 'Groups', icon: 'forum', route: '/app/groups' },
        { label: 'Messages', icon: 'chat', route: '/app/messages' },
      ],
    },
    {
      title: 'Practice',
      items: [
        { label: 'Matters', icon: 'folder_shared', route: '/app/matters', permission: 'matter:read' },
        { label: 'Documents', icon: 'description', route: '/app/documents', permission: 'document:read' },
        { label: 'Calendar', icon: 'event', route: '/app/calendar', permission: 'hearing:read' },
        { label: 'CRM', icon: 'contacts', route: '/app/crm', permission: 'lead:read' },
        { label: 'Clients', icon: 'badge', route: '/app/clients', permission: 'client:read' },
        { label: 'Billing', icon: 'payments', route: '/app/billing', permission: 'invoice:read' },
        { label: 'Payments', icon: 'account_balance_wallet', route: '/app/payments', permission: 'invoice:read' },
      ],
    },
    {
      title: 'Knowledge',
      items: [
        { label: 'Bare Acts', icon: 'library_books', route: '/app/knowledge', queryParams: { view: 'acts' }, permission: 'knowledge:read' },
        { label: 'Legal Research', icon: 'gavel', route: '/app/research', permission: 'research:use' },
        { label: 'Legal News', icon: 'newspaper', route: '/app/news' },
        { label: 'Knowledge Library', icon: 'menu_book', route: '/app/knowledge', queryParams: { view: 'firm' }, permission: 'knowledge:read' },
        { label: 'Marketplace', icon: 'storefront', route: '/app/marketplace', permission: 'marketplace:read' },
        { label: 'Analytics', icon: 'insights', route: '/app/analytics', permission: 'analytics:view' },
      ],
    },
    {
      // Single link to the Settings hub page — the sub-areas live there as tiles.
      items: [{ label: 'Settings', icon: 'settings', route: '/app/settings' }],
    },
  ];

  /** Groups with permission-filtered items; empty groups are dropped. */
  protected visibleGroups = computed(() =>
    this.navGroups
      .map((g) => ({
        ...g,
        items: g.items.filter((n) => !n.permission || this.auth.hasPermission(n.permission)),
      }))
      .filter((g) => g.items.length > 0),
  );

  /** The collapsible "Settings" group starts collapsed to keep the rail short. */
  protected readonly settingsExpanded = signal(false);
  protected toggleSettings(): void {
    this.settingsExpanded.update((v) => !v);
  }

  protected toggle(): void {
    this.opened.update((v) => !v);
  }

  protected async logout(): Promise<void> {
    this.realtime.disconnect();
    await this.auth.logout();
    location.assign('/auth/login');
  }
}

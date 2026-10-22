import { HelpControlsComponent } from '@features/help/help-controls.component';
import { TellAFriendService } from '@core/services/tell-a-friend.service';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { BreakpointObserver } from '@angular/cdk/layout';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
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
import { SampleDataService } from '@core/services/sample-data.service';
import { NotificationService } from '@core/services/notification.service';
import { firstValueFrom } from 'rxjs';
import { HttpClient } from '@angular/common/http';
import { joinPendingGroup } from '@core/groups/pending-invite';
import { takeNext } from '@core/navigation/after-signup';
import { isNativeApp } from '@core/platform/platform';
import { runningVersion, updateNow } from '@core/platform/live-update';

interface NavItem {
  label: string;
  icon: string;
  route: string;
  permission?: string;
  queryParams?: Record<string, string>;
  /** Only for platform administrators (is_superuser). */
  platformAdmin?: boolean;
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
    TermsUpdatePromptComponent, SupportDialogComponent, HelpControlsComponent,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  protected readonly auth = inject(AuthService);
  protected readonly theme = inject(ThemeService);
  private readonly realtime = inject(RealtimeService);
  private readonly samples = inject(SampleDataService);
  private readonly notify = inject(NotificationService);
  private readonly http = inject(HttpClient);
  private readonly shellRouter = inject(Router);
  protected readonly opened = signal(true);
  protected readonly compact = signal(false);
  protected readonly sampleDataAvailable = signal(false);
  protected readonly deletingSamples = signal(false);

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
    void this.loadSampleStatus();
    void this.joinInvitedGroup();
  }

  /** A group invite link opened before signing up or in: join it now and open the group. */
  private async joinInvitedGroup(): Promise<void> {
    const joined = await joinPendingGroup(this.http);
    if (joined) {
      this.notify.success(`You joined ${joined.name}.`);
      await this.shellRouter.navigate(['/app/groups', joined.group_id]);
      return;
    }
    // Signed up from a public page ("Save this section", "Judgments on …"): go there now.
    const next = takeNext();
    if (next && this.shellRouter.url !== next) await this.shellRouter.navigateByUrl(next);
  }

  private async loadSampleStatus(): Promise<void> {
    try {
      this.sampleDataAvailable.set((await firstValueFrom(this.samples.status())).available);
    } catch { /* The workspace remains usable if this optional status call fails. */ }
  }

  protected async deleteSampleData(): Promise<void> {
    if (this.deletingSamples()) return;
    const accepted = window.confirm(
      'Delete all VidhiSangh sample data from this organisation?\n\n' +
      'This removes the sample matters, hearings, documents and stored files, clients, CRM, calendar, billing, payments, knowledge and marketplace entries. Your own data will not be touched. This cannot be undone.',
    );
    if (!accepted) return;
    this.deletingSamples.set(true);
    try {
      await firstValueFrom(this.samples.clear());
      this.sampleDataAvailable.set(false);
      this.notify.success('Sample data deleted. The workspace is ready for your own work.');
    } catch {
      this.notify.error('Sample data could not be deleted. Please try again.');
    } finally {
      this.deletingSamples.set(false);
    }
  }

  protected readonly tellAFriend = inject(TellAFriendService);
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
        { label: 'My timesheets', icon: 'schedule', route: '/app/billing', queryParams: { section: 'timesheets' }, permission: 'timeentry:read' },
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
      items: [{ label: 'Settings', icon: 'settings', route: '/app/settings' },
        { label: 'Help & feature tour', icon: 'help_outline', route: '/app/help' },
        { label: 'Platform admin', icon: 'admin_panel_settings', route: '/app/platform-admin', platformAdmin: true }],
    },
  ];

  /** Groups with permission-filtered items; empty groups are dropped. */
  protected visibleGroups = computed(() =>
    this.navGroups
      .map((g) => ({
        ...g,
        items: g.items.filter((n) => (!n.permission || this.auth.hasPermission(n.permission))
          && (!n.platformAdmin || this.user()?.is_superuser === true)),
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

  /** Account menu in the app: which version is running, and "Update app". */
  protected readonly nativeApp = isNativeApp();
  protected readonly appVersion = signal<string | null>(null);
  protected readonly updatingApp = signal(false);

  protected loadAppVersion(): void {
    if (this.nativeApp) void runningVersion().then((v) => this.appVersion.set(v));
  }

  protected async updateApp(): Promise<void> {
    if (this.updatingApp()) return;
    this.updatingApp.set(true);
    this.notify.info('Checking for the latest version…');
    const result = await updateNow();
    // 'switching' reloads the screens; nothing more to do here.
    if (result === 'up-to-date') this.notify.success('You have the latest version.');
    else if (result === 'failed') this.notify.error('Could not update right now. Check your connection and try again.');
    if (result !== 'switching') this.updatingApp.set(false);
  }

  protected async logout(): Promise<void> {
    this.realtime.disconnect();
    await this.auth.logout();
    location.assign('/auth/login');
  }
}

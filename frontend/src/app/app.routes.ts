import { Routes } from '@angular/router';
import { authGuard } from '@core/guards/auth.guard';

/**
 * Top-level routing. Feature areas are lazy-loaded so the initial bundle stays
 * small; each maps to a functional module on the roadmap. Authenticated areas
 * sit under the app shell behind `authGuard`.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'app/dashboard' },

  {
    path: 'auth',
    loadChildren: () => import('@features/auth/auth.routes').then((m) => m.AUTH_ROUTES),
  },

  {
    // Public legal documents (DPDP s.5 notice; Terms with the DPA schedule).
    path: 'privacy',
    loadComponent: () =>
      import('@features/legal/privacy-notice.component').then((m) => m.PrivacyNoticeComponent),
  },
  {
    path: 'terms',
    loadComponent: () => import('@features/legal/terms.component').then((m) => m.TermsComponent),
  },
  {
    path: 'trust',
    loadComponent: () =>
      import('@features/legal/compliance-status.component').then((m) => m.ComplianceStatusComponent),
  },

  {
    // Public, login-free KYC form a client reaches from the tokenised link.
    path: 'kyc/:token',
    loadComponent: () =>
      import('@features/clients/kyc-form.component').then((m) => m.KycFormComponent),
  },

  {
    // Public, login-free client portal (magic-link token).
    path: 'portal/:token',
    loadComponent: () =>
      import('@features/portal/client-portal.component').then((m) => m.ClientPortalComponent),
  },

  {
    path: 'app',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./layout/shell/shell.component').then((m) => m.ShellComponent),
    children: [
      {
        path: 'dashboard',
        loadComponent: () =>
          import('@features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
      },
      {
        path: 'profile',
        loadComponent: () =>
          import('@features/profile/profile.component').then((m) => m.ProfileComponent),
      },
      {
        path: 'network',
        loadComponent: () =>
          import('@features/network/feed.component').then((m) => m.FeedComponent),
      },
      {
        path: 'people',
        loadComponent: () =>
          import('@features/network/people.component').then((m) => m.PeopleComponent),
      },
      {
        path: 'people/:id',
        loadComponent: () =>
          import('@features/network/person.component').then((m) => m.PersonComponent),
      },
      {
        path: 'groups',
        loadComponent: () =>
          import('@features/groups/groups.component').then((m) => m.GroupsComponent),
      },
      {
        path: 'groups/:id',
        loadComponent: () =>
          import('@features/groups/group-detail.component').then((m) => m.GroupDetailComponent),
      },
      {
        path: 'messages',
        loadComponent: () =>
          import('@features/messaging/messages.component').then((m) => m.MessagesComponent),
      },
      {
        path: 'matters',
        loadComponent: () =>
          import('@features/matters/matters.component').then((m) => m.MattersComponent),
      },
      {
        path: 'matters/:id',
        loadComponent: () =>
          import('@features/matters/matter-detail.component').then((m) => m.MatterDetailComponent),
      },
      {
        path: 'documents',
        loadComponent: () =>
          import('@features/documents/documents.component').then((m) => m.DocumentsComponent),
      },
      {
        // The full-page word processor for one draft.
        path: 'documents/drafts/:id',
        loadComponent: () =>
          import('@features/documents/draft-editor.component').then((m) => m.DraftEditorComponent),
      },
      {
        path: 'matters/:id/portal',
        loadComponent: () =>
          import('@features/portal/matter-portal.component').then((m) => m.MatterPortalComponent),
      },
      {
        path: 'calendar',
        loadComponent: () =>
          import('@features/calendar/calendar.component').then((m) => m.CalendarComponent),
      },
      {
        path: 'research',
        loadComponent: () =>
          import('@features/research/research.component').then((m) => m.ResearchComponent),
      },
      {
        // Before `research/:id` so "case" is not read as a judgment id.
        path: 'research/case/:cnr',
        loadComponent: () =>
          import('@features/research/case-detail.component').then((m) => m.CaseDetailComponent),
      },
      {
        path: 'research/:id',
        loadComponent: () =>
          import('@features/research/judgment-detail.component').then((m) => m.JudgmentDetailComponent),
      },
      {
        path: 'news',
        loadComponent: () =>
          import('@features/news/news.component').then((m) => m.NewsComponent),
      },
      {
        path: 'payments',
        loadComponent: () =>
          import('@features/payments/payments.component').then((m) => m.PaymentsComponent),
      },
      {
        path: 'crm',
        loadComponent: () =>
          import('@features/crm/crm.component').then((m) => m.CrmComponent),
      },
      {
        path: 'clients',
        loadComponent: () =>
          import('@features/clients/clients.component').then((m) => m.ClientsComponent),
      },
      {
        path: 'clients/:id',
        loadComponent: () =>
          import('@features/clients/client-detail.component').then((m) => m.ClientDetailComponent),
      },
      {
        path: 'crm/:id',
        loadComponent: () =>
          import('@features/crm/lead-detail.component').then((m) => m.LeadDetailComponent),
      },
      {
        path: 'billing',
        loadComponent: () =>
          import('@features/billing/billing.component').then((m) => m.BillingComponent),
      },
      {
        path: 'billing/:id',
        loadComponent: () =>
          import('@features/billing/invoice-detail.component').then((m) => m.InvoiceDetailComponent),
      },
      {
        path: 'knowledge',
        loadComponent: () =>
          import('@features/knowledge/knowledge.component').then((m) => m.KnowledgeComponent),
      },
      {
        path: 'knowledge/reader',
        loadComponent: () =>
          import('@features/knowledge/act-reader.component').then((m) => m.ActReaderComponent),
      },
      {
        path: 'marketplace',
        loadComponent: () =>
          import('@features/marketplace/marketplace.component').then((m) => m.MarketplaceComponent),
      },
      {
        path: 'analytics',
        loadComponent: () =>
          import('@features/analytics/analytics.component').then((m) => m.AnalyticsComponent),
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('@features/settings/settings-home.component').then(
            (m) => m.SettingsHomeComponent,
          ),
      },
      {
        path: 'settings/appearance',
        loadComponent: () =>
          import('@features/settings/appearance-settings.component').then(
            (m) => m.AppearanceSettingsComponent,
          ),
      },
      {
        path: 'settings/notifications',
        loadComponent: () =>
          import('@features/settings/notification-settings.component').then(
            (m) => m.NotificationSettingsComponent,
          ),
      },
      {
        path: 'settings/counsel-rates',
        loadComponent: () =>
          import('@features/settings/counsel-rates.component').then((m) => m.CounselRatesComponent),
      },
      {
        path: 'settings/security',
        loadComponent: () =>
          import('@features/settings/security-settings.component').then(
            (m) => m.SecuritySettingsComponent,
          ),
      },
      {
        // Privacy & data: export / delete my account, directory opt-out, org offboarding.
        path: 'settings/privacy',
        loadComponent: () =>
          import('@features/settings/privacy-settings.component').then(
            (m) => m.PrivacySettingsComponent,
          ),
      },
      {
        path: 'admin/feature-flags',
        loadComponent: () =>
          import('@features/admin/feature-flags.component').then((m) => m.FeatureFlagsComponent),
      },
      {
        path: 'admin/subscription',
        loadComponent: () =>
          import('@features/admin/subscription.component').then((m) => m.SubscriptionComponent),
      },
      {
        path: 'admin/users',
        loadComponent: () =>
          import('@features/admin/users.component').then((m) => m.UsersComponent),
      },
      {
        path: 'admin/audit',
        loadComponent: () =>
          import('@features/admin/audit-log.component').then((m) => m.AuditLogComponent),
      },
      {
        path: 'admin/system',
        loadComponent: () =>
          import('@features/admin/system.component').then((m) => m.SystemComponent),
      },
      {
        path: 'admin/webhooks',
        loadComponent: () =>
          import('@features/admin/webhooks.component').then((m) => m.WebhooksComponent),
      },
      {
        path: 'admin/api-keys',
        loadComponent: () =>
          import('@features/admin/api-keys.component').then((m) => m.ApiKeysComponent),
      },
      // ── Roadmap: lazy feature areas ─────────────────────────────
      // { path: 'network',   loadChildren: … },
      // { path: 'research',  loadChildren: … },
      // { path: 'matters',   loadChildren: … },
      // { path: 'documents', loadChildren: … },
      // { path: 'billing',   canActivate: [permissionGuard('billing:manage')], … },
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
    ],
  },

  { path: '**', redirectTo: 'app/dashboard' },
];

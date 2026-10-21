import { expect, test } from '@playwright/test';

const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Rao', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };
const ENTRY = { id: 'e1', user_id: 'u', counsel_name: 'Adv. Rao', source: 'manual', work_date: '2026-10-20', matter_number: 'M-2026-0012',
  client_name: 'Sharma Industries', description: 'Drafted written statement and list of documents', activity_type: 'drafting', billable: true,
  duration_minutes: 150, hourly_rate: '4000.00', amount: '10000.00', status: 'draft', rejection_reason: null, invoice_id: null };

test('timesheets fit a phone as cards, with the same actions', async ({ page }) => {
  await page.addInitScript(u => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, USER);
  await page.route('**/api/v1/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  await page.route('**/api/v1/billing/time-entries**', r => r.fulfill({ json: [ENTRY] }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app/billing?section=timesheets');
  const card = page.locator('article', { hasText: 'Drafted written statement' });
  await expect(card).toBeVisible();
  await expect(card.getByText('M-2026-0012')).toBeVisible();
  await expect(card.getByText(/2h 30m|2\.5/)).toBeVisible();
  await expect(card.getByRole('button', { name: 'Submit' })).toBeVisible();
  await expect(page.locator('table')).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

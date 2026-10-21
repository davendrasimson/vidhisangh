import { join } from 'node:path';
import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Rao', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };

test('choosing a colleague who acted for the other side shows a conflict warning', async ({ page }) => {
  const fixture = JSON.parse(readFileSync(join(__dirname, 'fixtures', 'matter.json'), 'utf8'));
  const matter = fixture.matter;
  await page.addInitScript(u => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, USER);
  await page.route('**/api/v1/matters/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/calendar/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  await page.route(`**/api/v1/matters/${matter.id}`, r => r.fulfill({ json: matter }));
  await page.route(`**/api/v1/matters/${matter.id}/timeline`, r => r.fulfill({ json: fixture.timeline }));
  await page.route('**/api/v1/matters/team/people', r => r.fulfill({ json: [
    { id: 'p', full_name: 'Adv. Past', email: null }, { id: 'c', full_name: 'Adv. Clean', email: null }] }));
  await page.route(/\/api\/v1\/matters\/[^/]+\/team\/conflicts\?/, r => r.fulfill({
    json: new URL(r.request().url()).searchParams.get('user_id') === 'p'
      ? [{ matter_id: 'o1', matter_number: 'M-0007', title: 'Gupta Builders v. State', party_name: 'Gupta Builders Ltd',
           kind: 'acted_for_opponent', current: true }]
      : [] }));

  await page.goto(`/app/matters/${matter.id}`);
  const pick = page.getByRole('combobox', { name: 'Add a colleague' });
  await pick.selectOption({ label: 'Adv. Past' });
  const warning = page.getByRole('alert', { name: 'Possible conflict' });
  await expect(warning).toContainText('Acted for Gupta Builders Ltd in M-0007 · Gupta Builders v. State (still on it)');
  await pick.selectOption({ label: 'Adv. Clean' });
  await expect(warning).toHaveCount(0);
  // Advisory only: adding is still possible.
  await expect(pick.locator('xpath=..').getByRole('button', { name: 'Add', exact: true })).toBeEnabled();
});

import { expect, test } from '@playwright/test';

const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Rao', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };

test('reassign panel shows who carries what and fills the form from it', async ({ page }) => {
  await page.addInitScript(u => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, USER);
  await page.route('**/api/v1/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  await page.route('**/api/v1/matters/field-settings', r => r.fulfill({ json: { fields: [], sections: [], standard_sections: {} } }));
  await page.route('**/api/v1/matters/team/people', r => r.fulfill({ json: [
    { id: 'b', full_name: 'Adv. Busy', email: null }, { id: 'f', full_name: 'Adv. Free', email: null }] }));
  await page.route('**/api/v1/matters/team/workload', r => r.fulfill({ json: [
    { user_id: 'b', full_name: 'Adv. Busy', open_matters: 12, lead_matters: 9, roles: { lead_counsel: 9, associate: 3 }, hearings_next_14_days: 7 },
    { user_id: 'f', full_name: 'Adv. Free', open_matters: 0, lead_matters: 0, roles: {}, hearings_next_14_days: 0 }] }));

  await page.goto('/app/matters');
  await page.getByRole('button', { name: 'Reassign matters' }).click();
  const table = page.getByRole('table', { name: 'Team workload' });
  await expect(table.getByRole('row', { name: /Adv\. Busy/ })).toContainText('12');
  await expect(table.getByRole('row', { name: /Adv\. Busy/ })).toContainText('Lead counsel 9 · Associate 3');
  await expect(table.getByRole('button', { name: 'Move matters from Adv. Free' })).toHaveCount(0);

  await table.getByRole('button', { name: 'Move matters from Adv. Busy' }).click();
  await table.getByRole('button', { name: 'Move matters to Adv. Free' }).click();
  await expect(page.getByRole('combobox', { name: 'Move from' })).toHaveValue('b');
  await expect(page.getByRole('combobox', { name: 'Move to' })).toHaveValue('f');
});

import { expect, test } from '@playwright/test';

const ADMIN = { id: 'a', tenant_id: 't', email: 'admin@example.com', full_name: 'Adv. Rao', is_active: true,
  is_email_verified: true, roles: ['org_admin'], permissions: [], mfa_enabled: false };
const LEAVER = { ...ADMIN, id: 'l', email: 'leaver@example.com', full_name: 'Adv. Leaving', roles: [] };
const STAYER = { ...ADMIN, id: 's', email: 'stayer@example.com', full_name: 'Adv. Staying', roles: [] };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAiYSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };

test('deactivating someone on open matters hands them over first', async ({ page }) => {
  await page.addInitScript(u => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, ADMIN);
  await page.route('**/api/v1/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: ADMIN }));
  await page.route(/\/api\/v1\/tenants\/users\?/, r => r.fulfill({ json: [ADMIN, LEAVER, STAYER] }));
  await page.route(/\/api\/v1\/matters\?/, r => r.fulfill({
    json: new URL(r.request().url()).searchParams.get('user_id') === 'l' ? [{ id: 'm1' }, { id: 'm2' }] : [] }));
  let transfer: Record<string, unknown> | null = null;
  await page.route('**/api/v1/matters/team/transfer', r => {
    transfer = r.request().postDataJSON();
    return r.fulfill({ json: { moved: 2, matter_numbers: ['M-1', 'M-2'] } });
  });
  const deactivated: string[] = [];
  await page.route('**/api/v1/tenants/users/*/deactivate', r => {
    deactivated.push(r.request().url().split('/').at(-2)!);
    return r.fulfill({ json: { ...LEAVER, is_active: false } });
  });

  await page.goto('/app/admin/users');
  await page.getByRole('button', { name: 'Deactivate Adv. Leaving' }).click();
  const panel = page.getByRole('group', { name: 'Hand over matters' });
  await expect(panel).toContainText('is on 2 open matters');
  await expect(panel.getByRole('button', { name: 'Hand over and deactivate' })).toBeDisabled();
  await panel.getByLabel('Hand over to').selectOption({ label: 'Adv. Staying' });
  await panel.getByRole('button', { name: 'Hand over and deactivate' }).click();

  await expect.poll(() => deactivated).toEqual(['l']);
  expect(transfer).toMatchObject({ from_user_id: 'l', to_user_id: 's', reason: 'left_firm' });
  await expect(panel).toBeHidden();
});

import { expect, test } from '@playwright/test';

const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Rao', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };
const PREVIEW = { group_id: '11111111-1111-4111-8111-111111111111', name: 'Karnal District Bar Association',
  description: 'Members of the Karnal bar', member_count: 41, is_verified: true };

test('an invite link: a new visitor is sent to sign up, then joined to the group on arrival', async ({ page }) => {
  await page.route('**/api/v1/groups/invite/abc12345', r => r.fulfill({ json: PREVIEW }));
  await page.goto('/join/abc12345');
  await expect(page.getByRole('heading', { name: /Karnal District Bar Association/ })).toBeVisible();
  await expect(page.getByText('41 members on VidhiSangh')).toBeVisible();
  await page.getByRole('link', { name: 'I have an account — sign in' }).click();
  await expect(page).toHaveURL(/\/auth\/login\?returnUrl=%2Fjoin%2Fabc12345/);
  expect(await page.evaluate(() => localStorage.getItem('vs_group_invite'))).toBe('abc12345');

  // Signed in (here: an existing session): the app joins the remembered group and opens it.
  let joined = false;
  await page.route('**/api/v1/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  await page.route('**/api/v1/groups/invite/abc12345/join', r => { joined = true; return r.fulfill({ json: PREVIEW }); });
  await page.evaluate((u) => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, USER);
  await page.goto('/app/dashboard');
  await expect.poll(() => joined).toBe(true);
  await expect(page).toHaveURL(/\/app\/groups\/11111111-1111-4111-8111-111111111111/);
  await expect(page.getByText('You joined Karnal District Bar Association.')).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('vs_group_invite'))).toBeNull();
});

test('an expired invite link says so', async ({ page }) => {
  await page.route('**/api/v1/groups/invite/old-code', r => r.fulfill({ status: 404, json: { detail: 'This invite link is not valid any more.' } }));
  await page.goto('/join/old-code');
  await expect(page.getByRole('heading', { name: 'This invite link has expired' })).toBeVisible();
});

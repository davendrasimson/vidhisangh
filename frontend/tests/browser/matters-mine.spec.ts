import { expect, test } from '@playwright/test';

const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Rao', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };

test('"My matters" asks the server for my matters and is remembered', async ({ page }) => {
  await page.addInitScript(u => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, USER);
  await page.route('**/api/v1/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  await page.route('**/api/v1/matters/field-settings', r => r.fulfill({ json: { fields: [], sections: [], standard_sections: {} } }));
  const asked: (string | null)[] = [];
  await page.route(/\/api\/v1\/matters\?/, r => { asked.push(new URL(r.request().url()).searchParams.get('user_id')); return r.fulfill({ json: [] }); });
  await page.goto('/app/matters');
  await expect.poll(() => asked.length).toBeGreaterThan(0);
  expect(asked.at(-1)).toBeNull();
  await page.getByRole('checkbox', { name: 'My matters' }).check();
  await expect.poll(() => asked.at(-1)).toBe('u');
  await page.reload();
  await expect(page.getByRole('checkbox', { name: 'My matters' })).toBeChecked();
  await expect.poll(() => asked.at(-1)).toBe('u');
});

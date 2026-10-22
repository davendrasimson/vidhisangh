import { expect, test } from '@playwright/test';

const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Rao', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };

test('on a phone the library tabs sit on one row, and "Bare Acts" opens the search ready to type', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(u => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, USER);
  await page.route('**/api/v1/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  await page.goto('/app/knowledge');

  const acts = page.getByRole('button', { name: /^Bare Acts/ });
  const firm = page.getByRole('button', { name: /^Firm library/ });
  const [a, f] = [await acts.boundingBox(), await firm.boundingBox()];
  expect(Math.abs(a!.y - f!.y)).toBeLessThan(4);  // same row
  expect(a!.height).toBeLessThan(60);               // one line, not wrapped

  await acts.click();
  await expect(page.getByRole('textbox', { name: 'Search exact statutory text' })).toBeFocused();
});

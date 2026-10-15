import { expect, test, type Page } from '@playwright/test';

// Signed in earlier on this device: the session marker and the cached profile exist.
const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Offline', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };

async function signedInBefore(page: Page) {
  await page.addInitScript(user => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user, scopes: ['*'] }));
  }, USER);
}

test('no connection when the app opens: stays signed in and shows the offline bar', async ({ page }) => {
  await signedInBefore(page);
  let online = false;
  await page.route('**/api/v1/auth/refresh', route => online ? route.fulfill({ json: PAIR }) : route.abort('internetdisconnected'));
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: USER }));
  await page.goto('/app/dashboard');
  await expect(page).toHaveURL(/\/app\/dashboard/);
  await expect(page.getByText(/Can't reach VidhiSangh right now/)).toBeVisible();
  await expect(page.getByText(/Welcome back/)).toHaveCount(0);

  online = true;
  await page.getByRole('button', { name: 'Retry now' }).click();
  await expect(page.getByText(/Can't reach VidhiSangh right now/)).toHaveCount(0, { timeout: 10_000 });
  await expect(page).toHaveURL(/\/app\/dashboard/);
});

test('a server restart (502) does not sign anyone out', async ({ page }) => {
  await signedInBefore(page);
  await page.route('**/api/v1/auth/refresh', route => route.fulfill({ status: 502, body: 'Bad Gateway' }));
  await page.goto('/app/dashboard');
  await expect(page).toHaveURL(/\/app\/dashboard/);
  await expect(page.getByText(/Can't reach VidhiSangh right now/)).toBeVisible();
});

test('a session the server really ended still goes to sign-in', async ({ page }) => {
  await signedInBefore(page);
  await page.route('**/api/v1/auth/refresh', route => route.fulfill({ status: 401, json: { detail: 'Refresh token revoked.' } }));
  await page.goto('/app/dashboard');
  await expect(page).toHaveURL(/\/auth\/login/);
});

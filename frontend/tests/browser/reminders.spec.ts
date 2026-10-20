import { expect, test, type Page } from '@playwright/test';

const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Rao', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false, phone: null, is_phone_verified: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };

async function signedIn(page: Page, user = USER) {
  await page.addInitScript(u => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, user);
  await page.route('**/api/v1/auth/refresh', route => route.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: user }));
  await page.route('**/api/v1/calendar/**', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/notifications/deliveries**', route => route.fulfill({ json: [] }));
}

test('turning on WhatsApp hearing reminders adds and verifies the mobile number first', async ({ page }) => {
  await signedIn(page);
  let saved: unknown;
  await page.route('**/api/v1/notifications/preferences', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/notifications/preferences/whatsapp', async route => {
    saved = route.request().postDataJSON();
    await route.fulfill({ json: { channel: 'whatsapp', enabled: true, types: [] } });
  });
  await page.route('**/api/v1/auth/me/phone/request', async route => {
    expect(route.request().postDataJSON()).toEqual({ phone: '+919876543210' });
    await route.fulfill({ json: { challenge_id: '7c401e3a-54b0-4d46-8d43-f8ee493fb060', expires_in: 300, detail: 'Code sent.' } });
  });
  await page.route('**/api/v1/auth/me/phone/verify', async route => {
    expect(route.request().postDataJSON()).toEqual({ challenge_id: '7c401e3a-54b0-4d46-8d43-f8ee493fb060', code: '123456' });
    await route.fulfill({ json: { ...USER, phone: '+919876543210', is_phone_verified: true } });
  });

  await page.goto('/app/settings/notifications');
  await expect(page.getByRole('heading', { name: /WhatsApp reminders of tomorrow's hearings/ })).toBeVisible();
  await page.getByLabel('Mobile number', { exact: true }).fill('+919876543210');
  await page.getByRole('button', { name: 'Send WhatsApp code' }).click();
  await page.getByLabel('WhatsApp code').fill('123456');
  await page.getByRole('button', { name: 'Verify and turn on' }).click();
  await expect(page.getByText('On · sent to +919876543210')).toBeVisible();
  expect(saved).toEqual({ enabled: true, types: [] });
  // The old "coming soon" WhatsApp channel row is gone.
  await expect(page.getByText('Coming soon — awaits WhatsApp Business.')).toHaveCount(0);
});

test('the diary suggests reminders until they are on, and "Not now" is remembered', async ({ page }) => {
  await signedIn(page, { ...USER, phone: '+919876543210', is_phone_verified: true });
  await page.route('**/api/v1/notifications/preferences', route => route.fulfill({ json: [] }));
  await page.goto('/app/calendar');
  const card = page.getByRole('heading', { name: /WhatsApp reminders of tomorrow's hearings/ });
  await expect(card).toBeVisible();
  await expect(page.getByRole('switch', { name: 'WhatsApp hearing reminders' })).toBeVisible();
  await page.getByRole('button', { name: 'Not now' }).click();
  await expect(card).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Calendar' })).toBeVisible();
  await expect(card).toHaveCount(0);
});

test('the diary says nothing once reminders are on', async ({ page }) => {
  await signedIn(page, { ...USER, phone: '+919876543210', is_phone_verified: true });
  await page.route('**/api/v1/notifications/preferences', route => route.fulfill({ json: [{ channel: 'whatsapp', enabled: true, types: [] }] }));
  await page.goto('/app/calendar');
  await expect(page.getByRole('heading', { name: 'Calendar' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /WhatsApp reminders/ })).toHaveCount(0);
});

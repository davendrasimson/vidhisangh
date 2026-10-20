import { expect, test, type Page } from '@playwright/test';

const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Asha Rao', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };

async function signedIn(page: Page) {
  await page.addInitScript(u => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, USER);
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
}

test('a member publishes a public profile page, shares it on WhatsApp and changes its address', async ({ page }) => {
  await signedIn(page);
  await page.route('**/api/v1/network/me/visibility', r => r.fulfill({ json: { discoverable: true } }));
  let state = { enabled: false, handle: null as string | null, url: null as string | null };
  const sent: unknown[] = [];
  await page.route('**/api/v1/network/me/public-page', async r => {
    if (r.request().method() === 'PUT') {
      const body = r.request().postDataJSON();
      sent.push(body);
      if (body.handle === 'taken') return r.fulfill({ status: 409, json: { detail: 'That address is taken. Try another.' } });
      const handle = body.handle ?? state.handle ?? 'asha-rao';
      state = { enabled: body.enabled, handle, url: `https://vidhisangh.com/in/${handle}/` };
    }
    await r.fulfill({ json: state });
  });
  await page.goto('/app/settings/privacy');
  await expect(page.getByRole('heading', { name: 'Public profile page' })).toBeVisible();
  await expect(page.getByText(/never your phone, email or address/)).toBeVisible();
  await page.getByRole('switch', { name: 'Public profile page' }).click();
  await expect(page.getByRole('link', { name: 'https://vidhisangh.com/in/asha-rao/' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Share on WhatsApp/ })).toHaveAttribute('href', /^https:\/\/wa\.me\/\?text=My%20profile%20on%20VidhiSangh%3A%20https%3A%2F%2Fvidhisangh\.com%2Fin%2Fasha-rao%2F$/);

  await page.getByRole('textbox', { name: 'Page address' }).fill('taken');
  await page.getByRole('button', { name: 'Change address' }).click();
  await expect(page.getByRole('alert')).toContainText('That address is taken');
  await page.getByRole('textbox', { name: 'Page address' }).fill('asha-rao-advocate');
  await page.getByRole('button', { name: 'Change address' }).click();
  await expect(page.getByRole('link', { name: 'https://vidhisangh.com/in/asha-rao-advocate/' })).toBeVisible();
  expect(sent).toEqual([{ enabled: true }, { enabled: true, handle: 'taken' }, { enabled: true, handle: 'asha-rao-advocate' }]);
});

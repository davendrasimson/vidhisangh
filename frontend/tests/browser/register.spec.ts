import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/auth/options', route => route.fulfill({ json: { whatsapp_available: true } }));
});

for (const firm of [false, true]) {
  test(`registration with ${firm ? 'firm name' : 'individual default'}`, async ({ page }) => {
    let submitted: Record<string, unknown> | undefined;
    await page.route('**/api/v1/auth/register', async route => {
      submitted = route.request().postDataJSON();
      await route.fulfill({ status: 409, json: { detail: 'Registration captured for test.' } });
    });
    await page.goto('/auth/register');
    await expect(page.getByRole('radio', { name: 'Individual practice', exact: true })).toBeChecked();
    await expect(page.getByLabel('Firm / chamber name')).toHaveCount(0);
    await page.getByLabel('Your full name').fill(' ');
    await expect(page.getByRole('button', { name: 'Create account', exact: true })).toBeDisabled();
    await page.getByLabel('Your full name').fill('Solo Advocate');
    await page.getByLabel('Email', { exact: true }).fill('solo@example.com');
    await page.getByLabel('Password', { exact: true }).fill('Str0ng!Pass#2026');
    await page.getByRole('checkbox', { name: /I agree/ }).check();
    const submit = page.getByRole('button', { name: 'Create account', exact: true });
    await expect(submit).toBeEnabled();
    if (firm) {
      await page.getByRole('radio', { name: 'Firm / chamber', exact: true }).check();
      await expect(submit).toBeDisabled();
      await page.getByLabel('Firm / chamber name').fill('  ');
      await expect(submit).toBeDisabled();
      await page.getByRole('radio', { name: 'Individual practice', exact: true }).check();
      await expect(submit).toBeEnabled();
      await page.getByRole('radio', { name: 'Firm / chamber', exact: true }).check();
      await page.getByLabel('Firm / chamber name').fill(' Example Chambers ');
    }
    await submit.click();
    await expect(page.getByRole('alert')).toContainText('Registration captured for test.');
    expect(submitted?.['practice_type']).toBe(firm ? 'firm' : 'individual');
    expect(submitted?.['organisation_name']).toBe(firm ? 'Example Chambers' : undefined);
  });
}

test('individual registration fits a phone without horizontal scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/auth/register');
  await expect(page.getByRole('radio', { name: 'Individual practice', exact: true })).toBeChecked();
  await expect(page.getByLabel('Your full name')).toBeVisible();
  await expect(page.getByLabel('Firm / chamber name')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/registration-mobile.png', fullPage: true });
});

test('switching back to individual omits a previously entered firm name', async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route('**/api/v1/auth/register', async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 409, json: { detail: 'Registration captured for test.' } });
  });
  await page.goto('/auth/register');
  await page.getByRole('radio', { name: 'Firm / chamber', exact: true }).check();
  await page.getByLabel('Firm / chamber name').fill('Old Chambers');
  await page.getByRole('radio', { name: 'Individual practice', exact: true }).check();
  await page.getByLabel('Your full name').fill('Solo Advocate');
  await page.getByLabel('Email', { exact: true }).fill('solo@example.com');
  await page.getByLabel('Password', { exact: true }).fill('Str0ng!Pass#2026');
  await page.getByRole('checkbox', { name: /I agree/ }).check();
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Registration captured for test.');
  expect(submitted?.['practice_type']).toBe('individual');
  expect(submitted?.['organisation_name']).toBeUndefined();
});

test('email signup waits for verification instead of opening the workspace', async ({ page }) => {
  let loadedUser = false;
  await page.route('**/api/v1/auth/register', route => route.fulfill({
    status: 201, json: { verification_required: true, detail: 'Check your email before signing in.' },
  }));
  await page.route('**/api/v1/auth/me', route => { loadedUser = true; return route.abort(); });
  await page.goto('/auth/register');
  await page.getByLabel('Your full name').fill('Email Advocate');
  await page.getByLabel('Email', { exact: true }).fill('email@example.com');
  await page.getByLabel('Password', { exact: true }).fill('Str0ng!Pass#2026');
  await page.getByRole('checkbox', { name: /I agree/ }).check();
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Resend verification link' })).toBeVisible();
  expect(loadedUser).toBe(false);
  await expect(page).toHaveURL(/auth\/register$/);
});

test('mobile signup requires a WhatsApp code and allows an empty email', async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  const challenge = '7c401e3a-54b0-4d46-8d43-f8ee493fb060';
  await page.route('**/api/v1/auth/whatsapp/request', async route => {
    expect(route.request().postDataJSON()).toEqual({ phone: '+919876543210', purpose: 'register' });
    await route.fulfill({ json: { challenge_id: challenge, expires_in: 300 } });
  });
  await page.route('**/api/v1/auth/register', async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 409, json: { detail: 'Mobile registration captured.' } });
  });
  await page.goto('/auth/register');
  await page.getByLabel('Your full name').fill('Mobile Advocate');
  await page.getByLabel('Password', { exact: true }).fill('Str0ng!Pass#2026');
  await page.getByRole('checkbox', { name: /I agree/ }).check();
  const submit = page.getByRole('button', { name: 'Create account', exact: true });
  await expect(submit).toBeDisabled();
  await page.getByLabel('Mobile number', { exact: true }).fill('+919876543210');
  await expect(submit).toBeDisabled();
  await page.getByRole('button', { name: 'Send WhatsApp code', exact: true }).click();
  await page.getByLabel('WhatsApp code', { exact: true }).fill('123456');
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.getByRole('alert')).toContainText('Mobile registration captured.');
  expect(submitted?.['email']).toBeNull();
  expect(submitted?.['phone']).toBe('+919876543210');
  expect(submitted?.['phone_challenge_id']).toBe(challenge);
  expect(submitted?.['phone_code']).toBe('123456');
  await page.getByLabel('Mobile number', { exact: true }).fill('+919876543211');
  await expect(submit).toBeDisabled();
  await expect(page.getByLabel('WhatsApp code', { exact: true })).toHaveCount(0);
});

test('WhatsApp alternative login sends the entered code and displays errors', async ({ page }) => {
  await page.route('**/api/v1/auth/whatsapp/request', route => route.fulfill({ json: {
    challenge_id: '7c401e3a-54b0-4d46-8d43-f8ee493fb060', expires_in: 300,
    detail: 'Code sent on WhatsApp.',
  } }));
  await page.route('**/api/v1/auth/whatsapp/login', async route => {
    expect(route.request().postDataJSON()['code']).toBe('123456');
    await route.fulfill({ status: 401, json: { detail: 'Incorrect WhatsApp code. Please try again.' } });
  });
  await page.goto('/auth/login');
  await page.getByRole('button', { name: 'Sign in with WhatsApp code' }).click();
  await page.getByLabel('Mobile number', { exact: true }).fill('+919876543210');
  await page.getByRole('button', { name: 'Send WhatsApp login code' }).click();
  await page.getByLabel('WhatsApp code', { exact: true }).fill('123456');
  await page.getByRole('button', { name: 'Verify and sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('Incorrect WhatsApp code');
});

test('email verification link confirms the address and offers sign-in', async ({ page }) => {
  await page.route('**/api/v1/auth/verify-email/test-token', route => route.fulfill({ json: { verified: true } }));
  await page.goto('/auth/verify-email/test-token');
  await expect(page.getByRole('heading', { name: 'Email confirmed' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Sign in', exact: true })).toHaveAttribute('href', '/auth/login');
});

test('email registration stays available when WhatsApp is not configured', async ({ page }) => {
  await page.route('**/api/v1/auth/options', route => route.fulfill({ json: { whatsapp_available: false } }));
  await page.goto('/auth/register');
  await expect(page.getByLabel('Mobile number', { exact: true })).toBeDisabled();
  await expect(page.getByText('WhatsApp verification is temporarily unavailable. You can register using email.')).toBeVisible();
  await page.getByLabel('Your full name').fill('Email Advocate');
  await page.getByLabel('Email', { exact: true }).fill('email@example.com');
  await page.getByLabel('Password', { exact: true }).fill('Str0ng!Pass#2026');
  await page.getByRole('checkbox', { name: /I agree/ }).check();
  await expect(page.getByRole('button', { name: 'Create account', exact: true })).toBeEnabled();
});

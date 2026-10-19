import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/auth/options', route => route.fulfill({ json: { whatsapp_available: true } }));
});

async function openEmailForm(page: import('@playwright/test').Page) {
  await page.goto('/auth/register');
  await page.getByRole('button', { name: /Sign up with email instead/ }).click();
}

async function fillEmailForm(page: import('@playwright/test').Page) {
  await page.getByLabel('Your full name').fill('Solo Advocate');
  await page.getByLabel('Email', { exact: true }).fill('solo@example.com');
  await page.getByRole('combobox', { name: 'I am a' }).click();
  await page.getByRole('option', { name: 'Advocate', exact: true }).click();
  await page.getByLabel('Password', { exact: true }).fill('Str0ng!Pass#2026');
  await page.getByRole('checkbox', { name: /I agree/ }).check();
}

test('sign-up opens on WhatsApp, with email one tap away', async ({ page }) => {
  await page.goto('/auth/register');
  await expect(page.getByLabel('Mobile number', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send WhatsApp code', exact: true })).toBeVisible();
  await expect(page.getByLabel('Password', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: /Sign up with email instead/ }).click();
  await expect(page.getByLabel('Password', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Firm / chamber name')).toHaveCount(0);
});

for (const firm of [false, true]) {
  test(`email registration ${firm ? 'for a firm' : 'as an individual'}`, async ({ page }) => {
    let submitted: Record<string, unknown> | undefined;
    await page.route('**/api/v1/auth/register', async route => {
      submitted = route.request().postDataJSON();
      await route.fulfill({ status: 409, json: { detail: 'Registration captured for test.' } });
    });
    await openEmailForm(page);
    await fillEmailForm(page);
    const submit = page.getByRole('button', { name: 'Create account', exact: true });
    await expect(submit).toBeEnabled();
    if (firm) {
      await page.getByRole('checkbox', { name: /registering a law firm or chamber/ }).check();
      await submit.click();
      await expect(page.getByRole('alert')).toContainText('your firm or chamber name');
      expect(submitted).toBeUndefined();
      await page.getByLabel('Firm / chamber name').fill(' Example Chambers ');
    }
    await submit.click();
    await expect(page.getByRole('alert')).toContainText('Registration captured for test.');
    expect(submitted?.['practice_type']).toBe(firm ? 'firm' : 'individual');
    expect(submitted?.['organisation_name']).toBe(firm ? 'Example Chambers' : undefined);
    expect(submitted?.['professional_role']).toBe('advocate');
    expect(submitted?.['add_sample_data']).toBe(firm);
  });
}

test('Create account on a phone says what is missing, next to the button', async ({ page }) => {
  let called = false;
  await page.route('**/api/v1/auth/register', route => { called = true; return route.abort(); });
  await page.setViewportSize({ width: 390, height: 844 });
  await openEmailForm(page);
  await page.getByLabel('Your full name').fill('Solo Advocate');
  await page.getByLabel('Email', { exact: true }).fill('solo@example.com');
  const submit = page.getByRole('button', { name: 'Create account', exact: true });
  await expect(submit).toBeEnabled();
  await submit.click();
  const alert = page.getByRole('alert');
  await expect(alert).toContainText('what best describes you');
  await expect(alert).toContainText('a password of at least 8 characters');
  await expect(alert).toContainText('agreement to the Terms of Service');
  await expect(alert).not.toContainText('your full name');
  await expect(alert).toBeInViewport();
  expect(called).toBe(false);
});

test('an email with the trailing space a phone keyboard adds is accepted and sent trimmed', async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route('**/api/v1/auth/register', async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 201, json: { verification_required: true, detail: 'Check your email.' } });
  });
  await openEmailForm(page);
  await fillEmailForm(page);
  await page.getByLabel('Email', { exact: true }).fill('solo@example.com ');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible();
  expect(submitted?.['email']).toBe('solo@example.com');
});

test('sign-up fits a phone without horizontal scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/auth/register');
  await expect(page.getByLabel('Mobile number', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/registration-mobile.png', fullPage: true });
});

test('email signup waits for verification instead of opening the workspace', async ({ page }) => {
  let loadedUser = false;
  await page.route('**/api/v1/auth/register', route => route.fulfill({
    status: 201, json: { verification_required: true, detail: 'Check your email before signing in.' },
  }));
  await page.route('**/api/v1/auth/me', route => { loadedUser = true; return route.abort(); });
  await openEmailForm(page);
  await fillEmailForm(page);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Resend verification link' })).toBeVisible();
  expect(loadedUser).toBe(false);
  await expect(page).toHaveURL(/auth\/register$/);
});

test('WhatsApp sign-up: number, code, name and role; email optional', async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route('**/api/v1/auth/whatsapp/request', async route => {
    expect(route.request().postDataJSON()).toEqual({ phone: '+919876543210', purpose: 'login' });
    await route.fulfill({ json: { challenge_id: '7c401e3a-54b0-4d46-8d43-f8ee493fb060', expires_in: 300, detail: 'Code sent.' } });
  });
  await page.route('**/api/v1/auth/whatsapp/login', route => route.fulfill({ json: {
    signup_required: true, signup_id: '1b4f0d6e-6f11-4f7e-9d0e-3d2b6c9f8a10', signup_token: 'x'.repeat(30), expires_in: 900,
  } }));
  await page.route('**/api/v1/auth/whatsapp/signup', async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 409, json: { detail: 'WhatsApp sign-up captured.' } });
  });
  await page.goto('/auth/register');
  await page.getByLabel('Mobile number', { exact: true }).fill('+919876543210');
  await page.getByRole('button', { name: 'Send WhatsApp code', exact: true }).click();
  await expect(page.getByRole('button', { name: /Resend code in/ })).toBeDisabled();
  await page.getByLabel('WhatsApp code', { exact: true }).fill('123456');
  await page.getByRole('button', { name: 'Verify and continue' }).click();
  await page.getByLabel('Full name').fill('Mobile Advocate');
  await page.getByRole('combobox', { name: 'I am a' }).click();
  await page.getByRole('option', { name: 'Law Student', exact: true }).click();
  await page.getByRole('checkbox', { name: /I agree/ }).check();
  await page.getByRole('button', { name: 'Create my account' }).click();
  await expect(page.getByRole('alert')).toContainText('WhatsApp sign-up captured.');
  expect(submitted?.['email']).toBeNull();
  expect(submitted?.['professional_role']).toBe('law_student');
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

test('email registration is the only form when WhatsApp is not configured', async ({ page }) => {
  await page.route('**/api/v1/auth/options', route => route.fulfill({ json: { whatsapp_available: false } }));
  await page.goto('/auth/register');
  await expect(page.getByLabel('Mobile number', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Use WhatsApp instead/ })).toHaveCount(0);
  await fillEmailForm(page);
  await expect(page.getByRole('button', { name: 'Create account', exact: true })).toBeEnabled();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('Continue with Google appears only when Google is configured, and starts the redirect', async ({ page }) => {
  await page.route('**/api/v1/auth/oauth/providers', route => route.fulfill({ json: [] }));
  await page.goto('/auth/register');
  await expect(page.getByRole('button', { name: /Sign up with email instead/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue with Google' })).toHaveCount(0);

  await page.unroute('**/api/v1/auth/oauth/providers');
  await page.route('**/api/v1/auth/oauth/providers', route => route.fulfill({ json: [{ name: 'google', display_name: 'Google' }] }));
  let redirectUri: string | undefined;
  await page.route('**/api/v1/auth/oauth/google/authorize', async route => {
    redirectUri = route.request().postDataJSON()['redirect_uri'];
    await route.fulfill({ json: { authorize_url: '/help?google=1', state: 's' } });
  });
  await page.goto('/auth/register');
  await expect(page.getByText(/By continuing with Google you agree/)).toBeVisible();
  await page.getByRole('button', { name: 'Continue with Google' }).click();
  await expect(page).toHaveURL(/help\?google=1/);
  expect(redirectUri).toMatch(/\/auth\/callback$/);
});

test('a new Google account lands on the profile to add a role', async ({ page }) => {
  await page.route('**/api/v1/auth/oauth/google/callback', async route => {
    expect(route.request().postDataJSON()).toMatchObject({ code: 'c', state: 's' });
    await route.fulfill({ json: {
      access_token: 'a.b.c', refresh_token: null, token_type: 'bearer', expires_in: 900, new_account: true,
    } });
  });
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: {
    id: 'u1', tenant_id: 't1', email: 'new@gmail.com', full_name: 'New Member', is_active: true,
    is_email_verified: true, roles: [], permissions: [], mfa_enabled: false,
  } }));
  await page.addInitScript(() => sessionStorage.setItem('vs_sso_provider', 'google'));
  await page.goto('/auth/callback?code=c&state=s');
  // The stub token is not a real session, so the guard may bounce to sign-in, keeping
  // /app/profile as the return address; either way the new account was sent to the profile.
  await expect(page).toHaveURL(/\/app\/profile$|returnUrl=%2Fapp%2Fprofile/);
});

test('sign-in always offers WhatsApp, even when the options check is refused', async ({ page }) => {
  await page.route('**/api/v1/auth/options', route => route.fulfill({ status: 429, json: { detail: 'Too many requests.' } }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/auth/login');
  const whatsapp = page.getByRole('button', { name: /Sign in with WhatsApp code/ });
  await expect(whatsapp).toBeEnabled();
  await expect(page.getByText(/Privileged and confidential/)).toHaveCount(0);
  await expect(page.getByLabel('Tip of the day')).toBeVisible();
  await page.screenshot({ path: 'test-results/login-mobile.png', fullPage: true });
  await whatsapp.click();
  await expect(page.getByLabel('Mobile number', { exact: true })).toBeVisible();
});

import { expect, Page, test } from '@playwright/test';

async function workspace(page: Page, scopes = ['*']) {
  await page.addInitScript(() => localStorage.setItem('vs.session', '1'));
  const token = ['e30', Buffer.from(JSON.stringify({ sub: 'test-user', tid: 'test-tenant', scopes, exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url'), 'test'].join('.');
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = [];
    if (path.endsWith('/auth/refresh')) json = { access_token: token, refresh_token: null, token_type: 'bearer', expires_in: 3600 };
    else if (path.endsWith('/auth/me')) json = { id: 'test-user', tenant_id: 'test-tenant', full_name: 'Test Advocate', email: 'test@example.invalid', is_active: true, roles: [], terms_version: 'test' };
    else if (path.endsWith('/privacy/notice')) json = { terms_version: 'test', notice_version: 'test' };
    else if (path.endsWith('/unread-count')) json = { count: 0 };
    else if (path.endsWith('/sample-data')) json = { available: false };
    else if (path.endsWith('/ws-ticket')) { await route.fulfill({ status: 503, json: { detail: 'Not used in UI fixtures' } }); return; }
    else if (path.endsWith('/feature-flags')) json = {};
    else if (path.endsWith('/matter-fields/settings')) json = { fields: [], sections: [], standard_sections: { additional: 'Additional information' } };
    else if (path.endsWith('/profile/me')) json = {};
    await route.fulfill({ json });
  });
}

test('public help home covers prominent features, searches and opens a deep-linked article', async ({ page }) => {
  await page.goto('/help');
  await expect(page.getByRole('heading', { name: 'Help & feature tour' })).toBeVisible();
  for (const name of ['Documents and e-signatures', 'Matters and custom forms', 'My timesheets', 'Bare Acts', 'Clients and KYC']) {
    await expect(page.getByRole('link', { name, exact: false }).first()).toBeVisible();
  }
  await page.screenshot({ path: 'test-results/help-home-desktop.png', fullPage: true });
  await page.getByLabel('Search help', { exact: true }).fill('Prepare for e-signature');
  await expect(page.getByText('1 topic', { exact: true })).toBeVisible();
  await page.locator('section[aria-labelledby="topics-title"]').getByRole('link', { name: /Documents and e-signatures/ }).click();
  await expect(page.locator('#guide-title')).toHaveText('Documents and e-signatures');
  await expect(page.locator('article')).toBeFocused();
  await page.reload();
  await expect(page.locator('#guide-title')).toHaveText('Documents and e-signatures');
  await page.getByRole('link', { name: 'All help topics', exact: true }).click();
  await page.getByLabel('Search help', { exact: true }).fill('no-such-feature-987');
  await expect(page.getByText(/No help topics match/)).toBeVisible();
});

test('feature tour supports back, next, finish and replay without leaving the page', async ({ page }) => {
  await page.goto('/help');
  await page.getByRole('button', { name: 'Take a feature tour' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: 'Back', exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(dialog.getByRole('heading', { name: 'Matters and custom forms' })).toBeVisible();
  await dialog.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(dialog.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  // Step until the last card; each step waits for the dialog to settle (a
  // count() straight after a click could see no "Next" mid-render and stop early).
  const finish = dialog.getByRole('button', { name: 'Finish tour' });
  await expect(async () => {
    if (await finish.isVisible()) return;
    await dialog.getByRole('button', { name: 'Next', exact: true }).click({ timeout: 2000 });
    throw new Error('more steps');
  }).toPass({ timeout: 30_000 });
  await finish.click();
  await expect(dialog).toHaveCount(0);
  await expect(page).toHaveURL(/\/help$/);
  await page.getByRole('button', { name: 'Take a feature tour' }).click();
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
});

test('matter help and light-bulb tips preserve an unfinished form and restore focus', async ({ page }) => {
  await workspace(page);
  await page.goto('/app/matters');
  await page.getByRole('button', { name: 'New matter', exact: true }).click();
  // The form's own field (not "the first input", which can be the search box before the form renders).
  const input = page.getByPlaceholder('Ramesh Kumar vs State of Haryana');
  await input.fill('Unsaved matter example');
  const trigger = page.getByRole('button', { name: 'Help for Matters and custom forms', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText(/Configure additional matter fields/)).toBeVisible();
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press('Tab');
    await expect.poll(() => page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  await expect(input).toHaveValue('Unsaved matter example');
  await page.getByRole('button', { name: 'Tips for Matters and custom forms', exact: true }).click();
  await expect(page.getByRole('dialog').getByText(/custom fields and sections/)).toBeVisible();
  await page.getByRole('dialog').getByRole('link', { name: 'Read full guide' }).click();
  await expect(page).toHaveURL(/\/app\/help\?topic=matters$/);
  await expect(page.locator('#guide-title')).toHaveText('Matters and custom forms');
});

test('page help updates after in-app navigation and explains e-signatures', async ({ page }) => {
  await workspace(page);
  await page.goto('/app/matters');
  await page.getByRole('link', { name: 'Documents', exact: true }).click();
  await page.getByRole('button', { name: 'Help for Documents and e-signatures', exact: true }).click();
  await expect(page.getByRole('dialog').getByText(/Prepare for e-signature/)).toBeVisible();
});

test('mobile help controls and popup fit at 320px in light and dark themes', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await workspace(page);
  await page.goto('/app/help?topic=documents');
  for (const dark of [false, true]) {
    await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark);
    const trigger = page.getByRole('button', { name: 'Help for Help and feature tour', exact: true });
    await expect(trigger).toBeVisible();
    expect(await trigger.evaluate(el => el.getBoundingClientRect().right)).toBeLessThanOrEqual(320);
    await page.getByRole('button', { name: 'Tips for Help and feature tour', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await page.screenshot({ path: `test-results/help-mobile-${dark ? 'dark' : 'light'}.png` });
    expect(await dialog.evaluate(el => el.getBoundingClientRect().right)).toBeLessThanOrEqual(320);
    await page.keyboard.press('Escape');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('public signing tips never copy the private token to a help URL', async ({ page }) => {
  await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: { detail: 'Expired test invitation' } }));
  await page.goto('/esign/PRIVATE_TEST_TOKEN');
  await page.getByRole('button', { name: 'Tips for Sign a document', exact: true }).click();
  await expect(page.getByRole('dialog').getByText(/new link/)).toBeVisible();
  await page.getByRole('dialog').getByRole('link', { name: 'Read full guide' }).click();
  await expect(page).toHaveURL(/\/help\?topic=sign$/);
});

test('restricted users get a tour of features available to their role', async ({ page }) => {
  await workspace(page, ['message:read']);
  await page.goto('/app/help');
  await page.getByRole('button', { name: 'Take a feature tour' }).click();
  const titles: string[] = [];
  const dialog = page.getByRole('dialog');
  for (let i = 0; i < 25; i++) {
    titles.push(await dialog.locator('h3').innerText());
    if (!await dialog.getByRole('button', { name: 'Next', exact: true }).count()) break;
    await dialog.getByRole('button', { name: 'Next', exact: true }).click();
  }
  expect(titles).toContain('Messages');
  expect(titles).not.toContain('Matters and custom forms');
  expect(titles).not.toContain('Billing and invoices');
});

test('help remains reachable across tablet and desktop navigation breakpoints', async ({ page }) => {
  await workspace(page);
  await page.goto('/app/help');
  for (const width of [768, 800, 960, 1024, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const trigger = page.getByRole('button', { name: 'Help for Help and feature tour', exact: true });
    await expect(trigger).toBeVisible();
    expect(await page.locator('.vs-topbar').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  }
});

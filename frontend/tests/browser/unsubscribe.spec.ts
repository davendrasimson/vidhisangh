import { expect, test } from '@playwright/test';

test('unsubscribe link: nothing happens until the person taps, then one tap removes them', async ({ page }) => {
  const posts: string[] = [];
  await page.route('**/api/v1/outreach/unsubscribe/**', r => { posts.push(r.request().url()); return r.fulfill({ status: 204 }); });
  await page.goto('/unsubscribe/tok123');
  await expect(page.getByRole('heading', { name: /Stop VidhiSangh invitation emails/ })).toBeVisible();
  await page.waitForTimeout(500);
  expect(posts).toHaveLength(0); // a mail scanner opening the page unsubscribes no one
  await page.getByRole('button', { name: 'Unsubscribe' }).click();
  await expect(page.getByRole('heading', { name: "You're unsubscribed" })).toBeVisible();
  expect(posts).toEqual([expect.stringMatching(/\/outreach\/unsubscribe\/tok123$/)]);
  await expect(page.locator('vs-public-footer')).toBeVisible();
});

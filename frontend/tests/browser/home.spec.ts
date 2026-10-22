import { expect, test, type Page } from '@playwright/test';

const SHOTS = process.env['HOME_SHOTS'];
const USER = { id: 'u', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Priya Sharma', is_active: true,
  is_email_verified: true, roles: ['org_admin'], permissions: [], mfa_enabled: false };
const PAIR = { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidSIsICJ0aWQiOiAidCIsICJleHAiOiA5OTk5OTk5OTk5LCAic2NvcGVzIjogWyIqIl19.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 };
const months = ['2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10'];
const overview = (matters: number) => ({
  revenue: { total_invoiced: 0, total_collected: 0, outstanding: 0, overdue_amount: 0 },
  matters: { open: matters, total: matters }, pipeline: { total_leads: 0, conversion_rate: 0, won_value: 0 },
  productivity: { upcoming_hearings: 1, hearings_next_7d: 1, open_tasks: 1, overdue_tasks: 0 },
  operations: { submitted_time_entries: 0, unbilled_time_value: 0, pending_signatures: 0, follow_ups_due: 0 },
  revenue_trend: months.map((m) => ({ month: m, invoiced: 0, collected: 0 })),
});
const DAILY = {
  section: { kind: 'section', ref: 'bns:318', post_id: 'p1', title: 'Section 318 BNS — Cheating', posted_at: '2026-10-22T02:30:00Z',
    description: 'Whoever, by deceiving any person, fraudulently or dishonestly induces the person so deceived to deliver any property…', url: 'https://vidhisangh.com/acts/bns/section-318/', site: 'VidhiSangh Bare Acts' },
  judgment: { kind: 'judgment', ref: 'j1', post_id: 'p2', title: 'Rao v. State of Karnataka', posted_at: '2026-10-22T02:30:00Z',
    description: 'Bail cannot be refused only because the charge sheet is long.', url: 'https://vidhisangh.com/judgments/j1/rao/', site: 'VidhiSangh Judgments' },
  news: [{ kind: 'news', ref: 'n1', post_id: 'p3', title: 'Supreme Court notifies winter vacation benches', posted_at: '2026-10-22T02:30:00Z',
    description: null, url: 'https://example.org/n1', site: 'Supreme Court of India' }],
};

async function home(page: Page, { matters, agenda }: { matters: number; agenda: unknown[] }) {
  await page.addInitScript((u) => {
    localStorage.setItem('vs.session', '1');
    localStorage.setItem('vs.profile-cache', JSON.stringify({ user: u, scopes: ['*'] }));
  }, USER);
  await page.route('**/api/v1/**', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', (r) => r.fulfill({ json: PAIR }));
  await page.route('**/api/v1/auth/me', (r) => r.fulfill({ json: USER }));
  await page.route('**/api/v1/tenants/current', (r) => r.fulfill({ json: { id: 't', name: USER.full_name } }));
  await page.route('**/api/v1/analytics/overview**', (r) => r.fulfill({ json: overview(matters) }));
  await page.route('**/api/v1/network/daily', (r) => r.fulfill({ json: DAILY }));
  await page.route(/\/api\/v1\/calendar\/agenda\?/, (r) => r.fulfill({ json: agenda }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app/dashboard');
}

test('a new member sees no wall of zeros: an invitation to add a case, search and the daily cards', async ({ page }) => {
  await home(page, { matters: 0, agenda: [] });
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening), Priya/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /Fetch a case by CNR/ })).toBeVisible();
  await expect(page.getByRole('article', { name: 'Section of the day' })).toContainText('Section 318 BNS');
  await expect(page.getByRole('article', { name: 'Judgment of the day' })).toContainText('Bail cannot be refused');
  await expect(page.getByText('Practice overview')).toHaveCount(0);
  await expect(page.getByText('Timesheets awaiting approval')).toHaveCount(0);
  await expect(page.getByText('Revenue trend')).toHaveCount(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/home-new.png`, fullPage: true });

  // The search goes to Bare Acts when that is chosen.
  await page.getByRole('radio', { name: 'Bare Acts' }).click();
  await page.getByRole('textbox', { name: 'Search the Bare Acts' }).fill('dishonestly induces');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page).toHaveURL(/\/app\/knowledge\?view=acts&q=dishonestly(%20|\+)induces/);
});

test('today\'s hearing is marked adjourned with the next date, and a task is ticked off, from home', async ({ page }) => {
  const today = new Date(); today.setHours(10, 30, 0, 0);
  const tomorrow = new Date(today.getTime() + 86_400_000);
  const agenda = [
    { kind: 'hearing', id: 'h1', title: 'Sharma v. Kumar — Arguments', start_at: today.toISOString(), end_at: null, all_day: false,
      event_type: 'court', status: 'scheduled', location: 'Delhi High Court', matter_id: 'm1', matter_number: 'M-0001',
      court: 'Delhi High Court', court_room: '12', item_number: '34' },
    { kind: 'deadline', id: 't1', title: 'File written statement', start_at: today.toISOString(), end_at: null, all_day: true,
      event_type: 'deadline', status: 'open', location: null, matter_id: 'm1', matter_number: 'M-0001' },
    { kind: 'hearing', id: 'h2', title: 'Gupta v. State — Bail', start_at: tomorrow.toISOString(), end_at: null, all_day: false,
      event_type: 'court', status: 'scheduled', location: 'Saket Court', matter_id: 'm2', matter_number: 'M-0002', court: 'Saket Court' },
  ];
  let patched: unknown; let created: unknown; let done = false;
  await home(page, { matters: 2, agenda });
  await page.route('**/api/v1/matters/hearings/h1', async (r) => { patched = r.request().postDataJSON(); await r.fulfill({ json: { id: 'h1' } }); });
  await page.route('**/api/v1/matters/m1/hearings', async (r) => { created = r.request().postDataJSON(); await r.fulfill({ status: 201, json: { id: 'h3' } }); });
  await page.route(/\/api\/v1\/matters\/tasks\/t1\/done/, async (r) => { done = true; await r.fulfill({ json: { id: 't1' } }); });

  const todayList = page.getByRole('list', { name: 'Today' });
  await expect(todayList).toContainText('Delhi High Court · Court 12 · Item 34');
  // Tomorrow's hearing cannot be marked yet.
  await expect(page.getByRole('list', { name: 'Tomorrow' }).getByRole('button', { name: 'Held' })).toHaveCount(0);
  await expect(page.getByText('Practice overview')).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/home-day.png`, fullPage: true });

  await todayList.getByRole('button', { name: 'Adjourned' }).click();
  await expect.poll(() => patched).toEqual({ status: 'adjourned' });
  const next = page.getByRole('form', { name: 'Next date' });
  await next.getByRole('textbox').first().fill('29/10/2026');
  await next.getByRole('textbox').first().press('Tab');
  await expect(next.getByRole('button', { name: 'Add to diary' })).toBeEnabled();
  await next.getByRole('button', { name: 'Add to diary' }).click();
  await expect.poll(() => created).toMatchObject({ court: 'Delhi High Court', court_room: '12' });

  await page.getByRole('checkbox', { name: 'Mark done: File written statement' }).check();
  await expect.poll(() => done).toBe(true);
});

test('"Fetch a case by CNR" opens the eCourts import on Matters', async ({ page }) => {
  await home(page, { matters: 0, agenda: [] });
  await page.route('**/api/v1/matters/field-settings', (r) => r.fulfill({ json: { fields: [], sections: [], standard_sections: {} } }));
  await page.getByRole('link', { name: /Fetch a case by CNR/ }).click();
  await expect(page.getByRole('heading', { name: 'Fetch a case from eCourts' })).toBeVisible();
});

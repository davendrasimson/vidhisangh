// Capture App Store screenshots from the live site at Apple's exact sizes.
//
//   REVIEW_PASSWORD=… node scripts/app-store-screenshots.mjs [out-dir]
//
// Signs in as the reviewer account (play-review@vidhisangh.com, a sample firm with
// fictional data; see docs/store/google-play/PUBLISHING.md step 6) and captures the
// screens listed below twice: iPhone 6.9" (1320×2868 = 440×956 CSS px at 3×) and
// iPad 13" (2064×2752 = 1032×1376 at 2×). Output: docs/store/app-store/<set>/NN-name.png.
// Screens that would show real members (People, Messages) are not captured.
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const BASE = process.env['SHOT_BASE_URL'] ?? 'https://vidhisangh.com';
const OUT = process.argv[2] ?? 'docs/store/app-store';
const PASSWORD = process.env['REVIEW_PASSWORD'];
if (!PASSWORD) throw new Error('REVIEW_PASSWORD is required');

const SCREENS = [
  ['01-daily', '/app/daily'],
  ['02-home', '/app/dashboard'],
  ['03-groups', '/app/groups'],
  ['04-research', '/app/research?q=anticipatory%20bail'],
  ['05-bare-act', '/app/knowledge/reader?act=bnss&section=481'],
  ['06-matters', '/app/matters'],
  ['07-calendar', '/app/calendar'],
  ['08-news', '/app/news'],
];
// Hidden while capturing: the sample-data banner, and the cards that list real members.
const HIDE = `
  .vs-sample-banner, [aria-labelledby="people-title"], [aria-labelledby="brief-people"],
  [aria-labelledby="network-title"] { display: none !important; }`;
const SETS = [
  { name: 'iphone-69', viewport: { width: 440, height: 956 }, scale: 3, mobile: true },
  { name: 'ipad-13', viewport: { width: 1032, height: 1376 }, scale: 2, mobile: false },
];

const only = process.env['SHOT_SETS']?.split(',');
const browser = await chromium.launch();
for (const set of SETS.filter((s) => !only || only.includes(s.name))) {
  const dir = join('..', OUT, set.name);
  await mkdir(dir, { recursive: true });
  const context = await browser.newContext({
    viewport: set.viewport, deviceScaleFactor: set.scale, isMobile: set.mobile, hasTouch: set.mobile,
    locale: 'en-IN', timezoneId: 'Asia/Kolkata', colorScheme: 'light',
    userAgent: set.mobile
      ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
      : 'Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
  });
  const page = await context.newPage();
  await page.goto(`${BASE}/auth/login`, { waitUntil: 'networkidle' });
  await page.getByLabel('Email').fill('play-review@vidhisangh.com');
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL(/\/app\//, { timeout: 60000 }).catch(async () => {
    console.error('sign-in did not navigate; page says:', (await page.locator('body').innerText()).slice(0, 300));
    throw new Error('sign-in failed');
  });
  await page.waitForTimeout(1500);
  for (const [name, path] of SCREENS) {
    await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
    // Never show a real member in a store screenshot, and hide the demo workspace's banner.
    await page.addStyleTag({ content: HIDE });
    await page.waitForTimeout(2500);
    await page.screenshot({ path: join(dir, `${name}.png`), fullPage: false });
    console.log(set.name, name);
  }
  await context.close();
  // The sign-in endpoint is rate-limited per address; let it breathe before the next set signs in.
  await new Promise((r) => setTimeout(r, 70000));
}
await browser.close();

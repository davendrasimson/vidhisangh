// The free calculators on /tools/: date arithmetic and the generated pages.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const { parseDate, parsePeriods, addPeriod } = createRequire(import.meta.url)('../scripts/tools.js');
const d = (s) => parseDate(s);
const iso = (t) => new Date(t).toISOString().slice(0, 10);

test('dates are dd/mm/yyyy and impossible dates are refused', () => {
  assert.equal(iso(d('10/01/2023')), '2023-01-10');
  assert.equal(d('31/02/2026'), null);
  assert.equal(d('2026-01-10'), null);
});

test('limitation: the first day is excluded (s. 12(1)), years and days counted on the calendar', () => {
  assert.equal(iso(addPeriod(d('10/01/2023'), parsePeriods('Three years.')[0])), '2026-01-10');
  assert.equal(iso(addPeriod(d('01/01/2026'), parsePeriods('Ninety days. Thirty days.')[0])), '2026-04-01');
  assert.equal(iso(addPeriod(d('01/01/2026'), parsePeriods('Ninety days. Thirty days.')[1])), '2026-01-31');
  assert.equal(iso(addPeriod(d('29/02/2024'), parsePeriods('One year.')[0])), '2025-02-28');
  assert.deepEqual(parsePeriods('Thirty years. Twelve years. Three years.').map((p) => p.n), [30, 12, 3]);
});

test('the Schedule has all 137 Articles and the tool pages are generated', () => {
  const schedule = JSON.parse(readFileSync(new URL('../content/limitation-schedule.json', import.meta.url), 'utf8'));
  assert.deepEqual(schedule.map((a) => a.article), Array.from({ length: 137 }, (_, i) => i + 1));
  assert.ok(schedule.every((a) => parsePeriods(a.period).length >= 1), 'every Article has a period');
  assert.equal(schedule[53].description, 'For specific performance of a contract.');
  assert.equal(schedule[53].period, 'Three years.');
  const art54 = readFileSync(new URL('../public/tools/limitation-calculator/article-54/index.html', import.meta.url), 'utf8');
  assert.match(art54, /<h1>Article 54: For specific performance of a contract<\/h1>/);
  assert.match(art54, /<option value="54" selected>/);
  assert.match(art54, /<script src="\/tools\/tools\.js\?v=[0-9a-f]{10}" defer><\/script>/);
  assert.match(readFileSync(new URL('../public/tools/default-bail-calculator/index.html', import.meta.url), 'utf8'), /Section 187\(3\) BNSS/);
  const sitemap = readFileSync(new URL('../public/sitemap.xml', import.meta.url), 'utf8');
  assert.ok(sitemap.includes('https://vidhisangh.com/tools/limitation-calculator/article-137/<'));
});

test('interest: simple and compound between two dates, 365-day year', async () => {
  const { interest } = createRequire(import.meta.url)('../scripts/tools.js');
  const simple = interest(100000, 9, d('01/01/2025'), d('01/01/2026'), 0);
  assert.equal(simple.days, 365);
  assert.equal(Math.round(simple.interest * 100) / 100, 9000);
  const yearly = interest(100000, 10, d('01/01/2024'), d('31/12/2025'), 1);
  assert.equal(yearly.days, 730);
  assert.equal(Math.round(yearly.total), 121000);  // 10% a year, twice
  const html = readFileSync(new URL('../public/tools/interest-calculator/index.html', import.meta.url), 'utf8');
  assert.match(html, /data-tool="interest"/);
  assert.match(html, /Section 34 of the Code of Civil Procedure/);
});

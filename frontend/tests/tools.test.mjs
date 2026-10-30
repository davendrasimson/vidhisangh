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

test('offence screener: the BNSS First Schedule is complete and the derived notes follow the Code', () => {
  const { maxTerm, defaultBailDays, arrestRegime, anticipatoryBail, screen } = createRequire(import.meta.url)('../scripts/tools.js');
  const data = JSON.parse(readFileSync(new URL('../content/bnss-first-schedule.json', import.meta.url), 'utf8'));
  // Every offence section of the BNS (49 to 357) has at least one entry; 1–48 define terms and exceptions.
  const sections = new Set(data.part_i.map((r) => r.section.replace(/\(.*$/, '')));
  for (const n of [49, 64, 103, 106, 303, 318, 351, 356, 357]) assert.ok(sections.has(String(n)), `section ${n}`);
  assert.ok(data.part_i.length > 450 && sections.size >= 285, `${data.part_i.length} rows, ${sections.size} sections`);
  for (const r of data.part_i) {
    assert.ok(['cognizable', 'non_cognizable', 'according'].includes(r.cognizable), `${r.section}: ${r.cognizable_text}`);
    assert.ok(['bailable', 'non_bailable', 'according'].includes(r.bailable), `${r.section}: ${r.bailable_text}`);
    assert.ok(r.offence.length > 4 && r.court.endsWith('.'), `${r.section}: ${r.offence} / ${r.court}`);
  }
  assert.equal(data.part_ii.length, 3);

  const theft = screen(data, '303(2)').rows;
  assert.equal(theft[0].offence, 'Theft.');
  assert.deepEqual([theft[0].cognizable, theft[0].bailable, theft[0].court], ['cognizable', 'non_bailable', 'Any Magistrate.']);
  assert.equal(screen(data, 'Section 303').rows.length, theft.length);     // the whole section when no sub-section is given
  const cheating = screen(data, 'IPC 420');
  assert.deepEqual(cheating.via, { ipc: '420', bns: ['318(4)'] });
  assert.equal(cheating.rows[0].punishment, 'Imprisonment for 7 years and fine.');
  assert.deepEqual(screen(data, '498A IPC').via.bns, ['85', '86']);
  assert.ok(screen(data, 'criminal intimidation').rows.some((r) => r.section === '351(2)'));
  assert.deepEqual(screen(data, '12').rows, []);                          // no offence in sections 1–48

  // Section 187(3): 90 days for death, life or ten years and upwards; else 60.
  const murder = screen(data, '103').rows[0];
  assert.deepEqual(maxTerm(murder.punishment), { death: true, life: true, years: null, fineOnly: false });
  assert.equal(defaultBailDays(maxTerm(murder.punishment)), 90);
  const rape = screen(data, '64(1)').rows[0];
  assert.equal(defaultBailDays(maxTerm(rape.punishment)), 90);          // not less than 10 years
  assert.equal(defaultBailDays(maxTerm(cheating.rows[0].punishment)), 60);
  assert.equal(maxTerm('Imprisonment for one month, or fine of 1,000 rupees, or both.').years, 1 / 12);
  assert.equal(maxTerm('Fine.').fineOnly, true);
  // Section 35(3): notice first when the offence is punishable up to 7 years.
  assert.equal(arrestRegime(maxTerm(cheating.rows[0].punishment), 'cognizable'), 'notice');
  assert.equal(arrestRegime(maxTerm(murder.punishment), 'cognizable'), 'arrest');
  assert.equal(arrestRegime(maxTerm('Imprisonment for 2 years.'), 'non_cognizable'), 'warrant');
  // Section 482(4): no anticipatory bail for sections 65 and 70(2).
  assert.equal(anticipatoryBail('65'), false);
  assert.equal(anticipatoryBail('70(2)'), false);
  assert.equal(anticipatoryBail('70(1)'), true);
  assert.equal(anticipatoryBail('318(4)'), true);

  // Section 359: both compounding tables, folded into the data file.
  const { compounding } = createRequire(import.meta.url)('../scripts/tools.js');
  const comp = JSON.parse(readFileSync(new URL('../content/bnss-compounding.json', import.meta.url), 'utf8')).rows;
  assert.equal(comp.filter((r) => r.part === 'victim').length, 37);
  assert.equal(comp.filter((r) => r.part === 'court').length, 13);
  assert.ok(comp.every((r) => r.sections.length && r.by.length > 8 && r.offence.length > 4));
  const served = JSON.parse(readFileSync(new URL('../public/tools/bnss-first-schedule.json', import.meta.url), 'utf8'));
  assert.equal(served.compounding.length, 50);
  assert.deepEqual(compounding(served, '303(2)'), { part: 'victim', by: 'The owner of the property stolen.', section: '303(2)' });
  assert.equal(compounding(served, '318(4)').part, 'court');
  assert.equal(compounding(served, '126(2)').by, 'The person restrained or confined.');   // "126(2), 127(2)"
  assert.equal(compounding(served, '136').section, '131, 133,136');
  assert.equal(compounding(served, '103(1)'), null);                                       // murder: not compoundable
  assert.equal(compounding(served, '115(2)').part, 'victim');
  assert.match(readFileSync(new URL('../src/app/features/knowledge/data/bnss-schedule-data.ts', import.meta.url), 'utf8'), /export const BNSS_COMPOUNDING/);

  const page = readFileSync(new URL('../public/tools/offence-screener/index.html', import.meta.url), 'utf8');
  assert.match(page, /data-tool="offence" data-src="\/tools\/bnss-first-schedule\.json\?v=[0-9a-f]{10}"/);
  assert.ok(JSON.parse(readFileSync(new URL('../public/tools/bnss-first-schedule.json', import.meta.url), 'utf8')).part_i.length === data.part_i.length);
  const readerData = readFileSync(new URL('../src/app/features/knowledge/data/bnss-schedule-data.ts', import.meta.url), 'utf8');
  assert.match(readerData, /export const BNSS_FIRST_SCHEDULE/);
});

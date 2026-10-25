import { test } from 'node:test';
import assert from 'node:assert/strict';

const { JUDICIAL_ORDER_FORMATS, ORDER_FIELD_LABELS, renderOrder, withOrderDefaults, orderStateFor } =
  await import('../src/app/features/documents/judicial-orders.ts');

// Labels the general drafting catalogue already provides (legal-drafting-templates.ts).
const COMMON = new Set(['court', 'place', 'caseNumber', 'firstParty', 'secondParty', 'orderDate', 'judgeName',
  'judgeDesignation', 'appearances', 'nextDate', 'orderBody', 'firNumber', 'policeStation', 'sections', 'amount']);
const placeholders = (text) => new Set([...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]));

test('the order set: 12 formats for review plus the general speaking and interim orders', () => {
  assert.equal(JUDICIAL_ORDER_FORMATS.length, 14);
  assert.equal(new Set(JUDICIAL_ORDER_FORMATS.map((f) => f.id)).size, 14);
  for (const f of JUDICIAL_ORDER_FORMATS) {
    assert.deepEqual(f.roles, ['judicial'], f.id);
    assert.equal(f.kind, 'order', f.id);
  }
});

test('every placeholder is a field of its format, the same in English and Hindi, and labelled', () => {
  for (const f of JUDICIAL_ORDER_FORMATS) {
    const en = placeholders(f.body.en);
    const hi = placeholders(f.body.hi);
    assert.deepEqual([...hi].sort(), [...en].sort(), `${f.id}: English and Hindi use different fields`);
    for (const key of en) assert.ok(f.fields.includes(key), `${f.id}: {{${key}}} is not one of its fields`);
    for (const key of f.fields) assert.ok(COMMON.has(key) || ORDER_FIELD_LABELS[key], `${f.id}: no label for ${key}`);
    for (const key of Object.keys(f.defaults ?? {})) assert.ok(f.fields.includes(key), `${f.id}: default for unknown ${key}`);
  }
});

test('headings follow the state: Allahabad practice for UP, Punjab & Haryana practice for Haryana', () => {
  const values = { court: 'Court of Additional Sessions Judge, Court No. 3', place: 'Agra', judgeName: 'A. Kumar',
    judgeDesignation: 'Additional Sessions Judge', officerCode: 'UP1234', caseNumber: 'S.T. 12/2025', cnr: 'UPAG010012342025',
    firstParty: 'State of Uttar Pradesh', secondParty: 'Ram', orderDate: '25/10/2026' };
  for (const f of JUDICIAL_ORDER_FORMATS) {
    for (const lang of ['en', 'hi', 'pa']) {
      for (const state of ['up', 'hr', 'general']) {
        const text = renderOrder(f, lang, state, values, ORDER_FIELD_LABELS);
        assert.ok(!text.includes('{{'), `${f.id}/${lang}/${state}: unfilled placeholder`);
        assert.ok(text.includes('S.T. 12/2025') && text.includes('Ram'), `${f.id}: case block missing`);
      }
    }
    const up = renderOrder(f, 'en', 'up', values, ORDER_FIELD_LABELS);
    assert.match(up, /^IN THE COURT OF Court of Additional Sessions Judge, Court No\. 3, Agra\nPresiding Officer: A\. Kumar/);
    assert.match(up, /JO Code: UP1234/);
    const hr = renderOrder(f, 'en', 'hr', values, ORDER_FIELD_LABELS);
    assert.match(hr, /^IN THE COURT OF A\. Kumar, Additional Sessions Judge, Agra\nUID No\. UP1234/);
    const hi = renderOrder(f, 'hi', 'up', values, ORDER_FIELD_LABELS);
    assert.match(hi, /^न्यायालय: /);
    assert.ok(hi.includes('बनाम'));
  }
});

test('judgments close as each High Court expects', () => {
  const judgment = JUDICIAL_ORDER_FORMATS.find((f) => f.id === 'judicial-criminal-judgment');
  const hr = renderOrder(judgment, 'en', 'hr', {}, ORDER_FIELD_LABELS);
  assert.ok(hr.includes('Announced in open court.'));
  assert.ok(hr.endsWith('Note: All the pages of this judgment have been checked and signed by me.'));
  const up = renderOrder(judgment, 'hi', 'up', {}, ORDER_FIELD_LABELS);
  assert.ok(up.includes('आज यह निर्णय मेरे द्वारा खुले न्यायालय में हस्ताक्षरित, दिनांकित कर उद्घोषित किया गया।'));
  assert.ok(up.includes('मु.अ.सं.'));
  const order = JUDICIAL_ORDER_FORMATS.find((f) => f.id === 'judicial-regular-bail');
  assert.ok(!renderOrder(order, 'en', 'hr', {}, ORDER_FIELD_LABELS).includes('Note: All the pages'));
});

test('standard wording switches with the language and state but never overwrites what was typed', () => {
  const bail = JUDICIAL_ORDER_FORMATS.find((f) => f.id === 'judicial-regular-bail');
  const en = withOrderDefaults(bail, 'en', {}, 'up');
  assert.match(en.conditions, /^\(i\) The applicant shall appear/);
  assert.equal(en.firstParty, 'State of Uttar Pradesh');
  const hi = withOrderDefaults(bail, 'hi', en, 'hr');
  assert.match(hi.conditions, /^\(i\) आवेदक/);
  assert.equal(hi.firstParty, 'हरियाणा राज्य');
  const typed = withOrderDefaults(bail, 'hi', { ...en, conditions: 'Report to the SHO every Monday.', firstParty: 'CBI' }, 'up');
  assert.equal(typed.conditions, 'Report to the SHO every Monday.');
  assert.equal(typed.firstParty, 'CBI');

  // A cheque complaint is complainant v. accused, not State v. accused.
  const ni = JUDICIAL_ORDER_FORMATS.find((f) => f.id === 'judicial-ni-138');
  assert.equal(withOrderDefaults(ni, 'en', { firstParty: 'State of Haryana' }, 'hr').firstParty, '');
  assert.equal(withOrderDefaults(ni, 'en', { firstParty: 'M/s Sharma Traders' }, 'hr').firstParty, 'M/s Sharma Traders');
});

test('the format set comes from the state in the profile', () => {
  assert.equal(orderStateFor('Uttar Pradesh'), 'up');
  assert.equal(orderStateFor('Haryana'), 'hr');
  assert.equal(orderStateFor('Delhi'), 'general');
  assert.equal(orderStateFor(null), 'general');
});

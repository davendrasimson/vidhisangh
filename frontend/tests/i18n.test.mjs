import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname;
const { HI } = await import('../src/app/core/i18n/hi.ts');
const { ACT_I18N, I18N_JS } = await import('../scripts/acts-i18n.mjs');

const DEVANAGARI = /[ऀ-ॣ०-ॿ]/;
const read = (p) => readFileSync(join(ROOT, p), 'utf8');

/** Every `'…' | t` in a template and every `i18n.t('…')` in a component. */
function keysIn(text) {
  const out = new Set();
  for (const m of text.matchAll(/'((?:[^'\\]|\\.)*)'\s*\|\s*t\b/g)) out.add(m[1].replace(/\\'/g, "'"));
  for (const m of text.matchAll(/"((?:[^"\\]|\\.)*)"\s*\|\s*t\b/g)) out.add(m[1]);
  for (const m of text.matchAll(/i18n\.t\('((?:[^'\\]|\\.)*)'\)/g)) out.add(m[1].replace(/\\'/g, "'"));
  return out;
}

const TRANSLATED = [
  'src/app/features/auth/register/register.component.html',
  'src/app/features/auth/register/register.component.ts',
  'src/app/features/auth/auth-layout.component.ts',
  'src/app/features/auth/professional-roles.ts',
  'src/app/features/calendar/calendar.component.html',
  'src/app/features/calendar/calendar.component.ts',
  'src/app/features/knowledge/act-reader.component.html',
];

test('every interface string piped through | t has Hindi, in Devanagari', () => {
  const missing = [];
  for (const file of TRANSLATED) {
    for (const key of keysIn(read(file))) if (!HI[key]) missing.push(`${file}: ${key}`);
  }
  // The role labels reach the template as data, so they are checked by value.
  for (const m of read('src/app/features/auth/professional-roles.ts').matchAll(/label: '([^']+)'/g)) if (!HI[m[1]]) missing.push(`role: ${m[1]}`);
  assert.deepEqual(missing, []);
  for (const [en, hi] of Object.entries(HI)) {
    assert.ok(DEVANAGARI.test(hi), `${en}: no Devanagari in "${hi}"`);
    assert.notEqual(hi.trim(), en.trim(), `${en}: untranslated`);
  }
});

test('the sign-up page, diary and reader are translated and the toggle is reachable', () => {
  assert.ok(keysIn(read('src/app/features/auth/register/register.component.html')).size >= 20);
  assert.ok(keysIn(read('src/app/features/calendar/calendar.component.html')).size >= 15);
  assert.ok(keysIn(read('src/app/features/knowledge/act-reader.component.html')).size >= 20);
  assert.match(read('src/app/features/auth/auth-layout.component.ts'), /<vs-language-toggle/);
  assert.match(read('src/app/layout/shell/shell.component.html'), /<vs-language-toggle/);
  assert.match(read('src/app/features/settings/appearance-settings.component.ts'), /Interface language/);
});

test('the static bare-act pages: every data-i18n string has Hindi and the switcher is a served file', () => {
  const build = read('scripts/build-act-pages.mjs');
  const keys = new Set([...build.matchAll(/data-i18n>([^<]+)</g)].map((m) => m[1].trim()));
  assert.ok(keys.size >= 10, 'data-i18n markers in the page builder');
  const missing = [...keys].filter((k) => !ACT_I18N[k]);
  assert.deepEqual(missing, []);
  for (const hi of Object.values(ACT_I18N)) assert.ok(DEVANAGARI.test(hi));
  assert.match(build, /<script src="\/acts\/i18n\.js" defer><\/script>/);
  assert.match(build, /writeFileSync\([^)]*'i18n\.js'\)?, I18N_JS\)/);
  assert.ok(I18N_JS.includes("'vs.lang'") && I18N_JS.includes('data-i18n'));
  assert.ok(!I18N_JS.includes('</script'), 'the switcher never closes a script tag');
});

// Sign-up errors: the person sees why the server refused, not "Request validation failed."
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const { problemMessage } = await import('../src/app/core/http/problem-message.ts');

const invalid = (errors) => ({ status: 422, error: { detail: 'Request validation failed.', errors } });

test('a 422 shows the field reason, not the generic detail', () => {
  assert.equal(
    problemMessage(invalid([{ loc: ['body', 'password'], msg: 'Value error, This password is too common or appears in breached-password lists. Choose something less guessable.', type: 'value_error' }]), 'x'),
    'This password is too common or appears in breached-password lists. Choose something less guessable.',
  );
  assert.equal(
    problemMessage(invalid([{ loc: ['body', 'email'], msg: 'value is not a valid email address: The part after the @-sign is not valid. It should have a period.', type: 'value_error' }]), 'x'),
    'Enter a valid email address (The part after the @-sign is not valid. It should have a period).',
  );
  assert.equal(problemMessage(invalid([{ loc: ['body', 'full_name'], msg: 'Field required', type: 'missing' }]), 'x'), 'Full name is required.');
  assert.equal(
    problemMessage(invalid([{ loc: ['body', 'full_name'], msg: 'String should have at least 2 characters', type: 'string_too_short' }]), 'x'),
    'Full name: String should have at least 2 characters',
  );
});

test('other errors keep their detail; a rate limit says how long to wait', () => {
  assert.equal(problemMessage({ status: 401, error: { detail: 'Incorrect WhatsApp code. Please try again.' } }, 'x'), 'Incorrect WhatsApp code. Please try again.');
  assert.equal(problemMessage({ status: 429, error: { detail: 'Too many requests.', errors: { retry_after: 42 } } }, 'x'), 'Too many attempts. Please wait 42 seconds and try again.');
  assert.equal(problemMessage({ status: 429, error: { detail: 'Too many requests.', errors: { retry_after: 1800 } } }, 'x'), 'Too many attempts. Please wait 30 minutes and try again.');
  assert.equal(problemMessage({ status: 0 }, 'x'), 'Cannot reach the server. Check your connection.');
  assert.equal(problemMessage({ status: 500, error: null }, 'Registration failed.'), 'Registration failed.');
});

test('sign-up screens use it, count down before a new code and check emails like the server', async () => {
  const { STRICT_EMAIL } = await import('../src/app/features/auth/send-code-cooldown.ts');
  for (const ok of ['ravi@gmail.com', 'a.b@firm.co.in']) assert.ok(STRICT_EMAIL.test(ok), ok);
  for (const bad of ['ravi@gmail', 'ravi@gmail.', 'ravi kumar@gmail.com', 'ravi@@gmail.com']) assert.ok(!STRICT_EMAIL.test(bad), bad);
  for (const file of ['register/register.component.ts', 'whatsapp-login.component.ts']) {
    const src = readFileSync(new URL(`../src/app/features/auth/${file}`, import.meta.url), 'utf8');
    assert.ok(!/error\?\.detail \?\?/.test(src), `${file} still shows only the generic detail`);
    assert.match(src, /problemMessage\(err/);
  }
  const whatsapp = readFileSync(new URL('../src/app/features/auth/whatsapp-login.component.ts', import.meta.url), 'utf8');
  assert.match(whatsapp, /this\.cooldown\.start\(\)/);
});

test('sign-up starts with WhatsApp; email is the alternative and firm questions only for firms', () => {
  const html = readFileSync(new URL('../src/app/features/auth/register/register.component.html', import.meta.url), 'utf8');
  const ts = readFileSync(new URL('../src/app/features/auth/register/register.component.ts', import.meta.url), 'utf8');
  assert.ok(html.indexOf('<app-whatsapp-login mode="join"') < html.indexOf('formControlName="email"'), 'WhatsApp comes first');
  assert.match(html, /Sign up with email instead/);
  assert.match(html, /formControlName="professional_role"/);
  // Firm name and the sample workspace sit inside the firm branch, not in the default form.
  const firm = html.slice(html.indexOf('@if (form.controls.firm.value)'));
  assert.ok(firm.includes('formControlName="organisation_name"') && firm.includes('formControlName="add_sample_data"'));
  assert.ok(!html.includes('formControlName="phone"'), 'the email form no longer asks for a phone');
  assert.match(ts, /add_sample_data: values\.firm && values\.add_sample_data/);
  const whatsapp = readFileSync(new URL('../src/app/features/auth/whatsapp-login.component.ts', import.meta.url), 'utf8');
  assert.match(whatsapp, /Email \(optional\)/);
  assert.match(whatsapp, /email: this\.email\.trim\(\) \|\| null/);
});

test('a WhatsApp code in progress survives the app restarting, and expires with the code', async () => {
  const { loadPending, savePending, clearPending, PENDING_KEY } = await import('../src/app/features/auth/whatsapp-pending.ts');
  const mem = new Map();
  const s = { getItem: k => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v), removeItem: k => mem.delete(k) };
  const now = 1_000_000;
  savePending({ phone: '+919876543210', challenge: 'c1', expiresAt: now + 300_000, resendAt: now + 60_000 }, s);
  assert.equal(loadPending(now + 120_000, s)?.challenge, 'c1');
  assert.equal(loadPending(now + 301_000, s), null, 'gone once the code has expired');
  assert.ok(!mem.has(PENDING_KEY));
  // A sign-up pass outlives the code it came from, until its own deadline.
  savePending({ phone: '+919876543210', challenge: null, expiresAt: 0, resendAt: 0, signup: { signup_id: 'i', signup_token: 't', expiresAt: now + 900_000 } }, s);
  assert.equal(loadPending(now + 600_000, s)?.signup?.signup_id, 'i');
  clearPending(s);
  assert.equal(loadPending(now, s), null);
  mem.set(PENDING_KEY, '{not json');
  assert.equal(loadPending(now, s), null);

  const ts = readFileSync(new URL('../src/app/features/auth/whatsapp-login.component.ts', import.meta.url), 'utf8');
  assert.match(ts, /const pending = loadPending\(\)/, 'the form restores a saved code');
  assert.match(ts, /savePending\(\{ phone, challenge: result\.challenge_id/);
  const login = readFileSync(new URL('../src/app/features/auth/login/login.component.ts', import.meta.url), 'utf8');
  assert.match(login, /signal\(loadPending\(\) !== null/, 'sign-in reopens on WhatsApp while a code is waiting');
});

test('app updates are applied at launch, never when the app goes to the background', () => {
  const src = readFileSync(new URL('../src/app/core/platform/live-update.ts', import.meta.url), 'utf8');
  assert.ok(!/updater\.next\(/.test(src), 'next() installs on backgrounding (e.g. while reading a WhatsApp code)');
  assert.match(src, /setMultiDelay\(\{ delayConditions: \[\{ kind: 'kill' \}\] \}\)/);
  assert.match(src, /updater\.set\(\{ id: target\.id \}\)/);
});

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
    assert.match(src, /this\.cooldown\.start\(\)/);
  }
});

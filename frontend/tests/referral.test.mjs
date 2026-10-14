// Invite links (?ref=CODE): the code is kept until sign-up and sent with it.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
const { captureReferral, pendingReferral, clearReferral } = await import('../src/app/core/services/referral-capture.ts');

test('a valid invite code is kept until sign-up, junk is ignored', () => {
  captureReferral('?utm_source=tell_a_friend&ref=ab7k2mq');
  assert.equal(pendingReferral(), 'AB7K2MQ');
  captureReferral('?ref=<script>');        // not a code: the kept one stays
  captureReferral('?ref=O0I1');            // letters we never issue
  assert.equal(pendingReferral(), 'AB7K2MQ');
  clearReferral();
  assert.equal(pendingReferral(), null);
});

test('sign-up sends the kept code and the app captures it on every page', () => {
  const auth = readFileSync(new URL('../src/app/core/auth/auth.service.ts', import.meta.url), 'utf8');
  assert.match(auth, /referral_code: pendingReferral\(\)/);
  assert.match(readFileSync(new URL('../src/app/app.ts', import.meta.url), 'utf8'), /captureReferral\(window\.location\.search\)/);
});

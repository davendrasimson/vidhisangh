// Guards for the Android / iOS app (Capacitor). The app bundles this Angular
// build, so a few web habits silently break it; these tests catch them.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = new URL('..', import.meta.url).pathname;
const read = (path) => readFileSync(join(root, path), 'utf8');

function sources(dir, out = []) {
  for (const name of readdirSync(join(root, dir))) {
    const rel = join(dir, name);
    if (statSync(join(root, rel)).isDirectory()) sources(rel, out);
    else if (/\.(ts|html)$/.test(name) && !name.endsWith('.spec.ts')) out.push(rel);
  }
  return out;
}

test('the app talks to the canonical public host over https', () => {
  const env = read('src/environments/environment.mobile.ts');
  // www.vidhisangh.com has no WebSocket route, so real-time updates would fail there.
  assert.match(env, /apiBaseUrl: 'https:\/\/vidhisangh\.com\/api\/v1'/);
  assert.match(env, /publicAppUrl: 'https:\/\/vidhisangh\.com'/);
});

test('capacitor serves the mobile build and keeps native HTTP on, logging off', () => {
  const cap = read('capacitor.config.ts');
  const angular = JSON.parse(read('angular.json'));
  const build = Object.values(angular.projects)[0].architect.build;
  const mobile = build.configurations.mobile;
  assert.equal(mobile.serviceWorker, false, 'no service worker inside the app');
  assert.ok(mobile.fileReplacements.some((r) => r.with.endsWith('environment.mobile.ts')));
  assert.notEqual(mobile.outputPath, build.options.outputPath, 'app build must never land in the web dist');
  assert.ok(cap.includes(`webDir: '${mobile.outputPath}/browser'`), 'webDir must match the mobile outputPath');
  assert.match(cap, /CapacitorHttp: \{ enabled: true \}/, 'session cookie needs native HTTP');
  assert.match(cap, /loggingBehavior: 'none'/, 'bridge logs print tokens and passwords');
});

test('downloads go through the shared saveBlob helper', () => {
  // `<a download>` does nothing in a WebView; saveBlob hands the file to the share sheet.
  const offenders = sources('src/app').filter((file) => {
    if (file.includes('core/platform/')) return false;
    const text = read(file);
    return /\.download\s*=/.test(text) || /createObjectURL\([^)]*\)[\s\S]{0,200}\.click\(\)/.test(text);
  });
  assert.deepEqual(offenders, []);
});

test('links meant for other people use publicOrigin(), not the page origin', () => {
  // Inside the app location.origin is https://localhost, which nobody else can open.
  const offenders = sources('src/app').filter((file) => {
    const text = read(file);
    return /`\$\{(?:window\.)?location\.origin\}\/(?:pay|portal|app|kyc|sign)\b/.test(text);
  });
  assert.deepEqual(offenders, []);
});

test('the page never asks for viewport-fit=cover (app would draw under the system bars)', () => {
  // Capacitor's SystemBars checks the viewport once at load. With `cover` on
  // WebView 140+ it hands the insets to page CSS, and this app has none.
  assert.doesNotMatch(read('src/index.html'), /viewport-fit\s*=\s*cover/);
});

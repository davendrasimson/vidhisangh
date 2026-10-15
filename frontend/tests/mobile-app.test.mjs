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

test('live screen updates come only from vidhisangh.com, never the Capgo cloud', () => {
  const cap = read('capacitor.config.ts');
  const block = cap.slice(cap.indexOf('CapacitorUpdater: {'), cap.indexOf('},', cap.indexOf('CapacitorUpdater: {')));
  assert.match(block, /autoUpdate: false/, 'the app decides when to download');
  assert.match(block, /statsUrl: ''/, 'stats and health reporting off');
  assert.match(block, /channelUrl: ''/, 'channel calls off');
  assert.match(block, /resetWhenUpdate: true/, 'a store update drops downloaded screens');
  assert.doesNotMatch(block, /capgo\.app/);
  // Without notifyAppReady the plugin rolls every update back.
  assert.match(read('src/app/core/platform/native-shell.ts'), /await initLiveUpdates\(\)/);
});

test('a published release is used only by the native build it was made for', async () => {
  const { releaseFor } = await import('../src/app/core/platform/live-update.ts');
  const files = [{ name: 'index.html', sha256: 'a'.repeat(64) }];
  const manifest = { android: { 4: { version: '1.0.3-web.1', files } } };
  assert.equal(releaseFor(manifest, 'android', '4')?.version, '1.0.3-web.1');
  assert.equal(releaseFor(manifest, 'android', '5'), null);
  assert.equal(releaseFor(manifest, 'ios', '4'), null);
  assert.equal(releaseFor({ android: { 4: { version: 'x', files: [{ name: 'a', sha256: 'nothex' }] } } }, 'android', '4'), null);
  assert.equal(releaseFor(null, 'android', '4'), null);
});

test('background reconnects never toast "Cannot reach the server"', () => {
  // A phone in the background has no network; the realtime socket used to retry
  // every 3 s and every failed ticket request showed the error toast.
  const realtime = read('src/app/core/services/realtime.service.ts');
  assert.match(realtime, /ws-ticket`, \{\}, \{\s*context: new HttpContext\(\)\.set\(SILENT_ERRORS, true\)/);
  assert.match(realtime, /visibilityState !== 'visible' \|\| !navigator\.onLine\) return;\s*this\.reconnectTimer/);
  assert.match(realtime, /addEventListener\('visibilitychange'/);
  assert.match(realtime, /addEventListener\('online'/);
  const delays = [0, 1, 2, 3, 4, 5, 10].map((n) => Math.min(3000 * 2 ** n, 60_000));
  assert.match(realtime, /Math\.min\(3000 \* 2 \*\* Math\.max\(attempt, 0\), 60_000\)/);
  assert.deepEqual(delays, [3000, 6000, 12000, 24000, 48000, 60000, 60000]);
  // And no connection toast at all while the app is hidden.
  assert.match(read('src/app/core/interceptors/error.interceptor.ts'), /err\.status === 0 && typeof document !== 'undefined' && document\.visibilityState === 'hidden'/);
});

test('the app bundle leaves out the public bare-act web pages', () => {
  // public/acts/ holds ~3,800 generated SEO pages (~46 MB). The app reads Acts
  // from its own offline library; shipping the pages would bloat the store
  // bundle and every live update.
  const angular = JSON.parse(read('angular.json'));
  const mobile = Object.values(angular.projects)[0].architect.build.configurations.mobile;
  assert.ok(mobile.assets?.some((a) => a.input === 'public' && a.ignore?.includes('acts/**')));
});

test('the app stays signed in when the server cannot be reached', () => {
  const read = (f) => readFileSync(new URL(`../src/app/${f}`, import.meta.url), 'utf8');
  const interceptor = read('core/interceptors/auth.interceptor.ts');
  assert.match(interceptor, /isNativeApp\(\) && req\.url\.startsWith\(environment\.apiBaseUrl\)/);
  assert.match(interceptor, /'X-VidhiSangh-Client': 'app'/);
  const auth = read('core/auth/auth.service.ts');
  // Only 401/403 ends a session; anything else (offline, 502) keeps the person signed in.
  assert.match(auth, /if \(status === 401 \|\| status === 403\) \{\s*this\.tokens\.dropAccessToken\(\);[\s\S]*?return false;\s*\}\s*\/\/[^\n]*\n[^\n]*\n\s*return this\.enterOffline\(\);/);
  assert.match(read('layout/shell/shell.component.html'), /auth\.offline\(\)/);
});

// Guards for the Android / iOS app (Capacitor). The app bundles this Angular
// build, so a few web habits silently break it; these tests catch them.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
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

test('app links: only the app\'s own screens on vidhisangh.com open in the app', async () => {
  const { appLinkPath, APP_LINK_PREFIXES } = await import('../src/app/core/platform/app-links.ts');
  assert.equal(appLinkPath('https://vidhisangh.com/join/AbC123'), '/join/AbC123');
  assert.equal(appLinkPath('https://www.vidhisangh.com/app/matters/1?tab=fees#x'), '/app/matters/1?tab=fees#x');
  assert.equal(appLinkPath('https://vidhisangh.com/auth/reset/tok?invite=1'), '/auth/reset/tok?invite=1');
  assert.equal(appLinkPath('https://vidhisangh.com/acts/bns/section-1/'), null, 'public pages stay in the browser');
  assert.equal(appLinkPath('https://vidhisangh.com/in/rao/'), null);
  assert.equal(appLinkPath('http://vidhisangh.com/app/x'), null);
  assert.equal(appLinkPath('https://evil.example/app/x'), null);
  assert.equal(appLinkPath('https://vidhisangh.com.evil.example/app/x'), null);
  assert.equal(appLinkPath('not a url'), null);
  // The manifest claims exactly these paths.
  const manifest = read('android/app/src/main/AndroidManifest.xml');
  const claimed = [...manifest.matchAll(/android:pathPrefix="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(claimed.sort(), [...APP_LINK_PREFIXES].sort());
  assert.match(manifest, /android:autoVerify="true"/);
});

test('assetlinks.json names the app and at least the upload key', () => {
  const links = JSON.parse(read('public/.well-known/assetlinks.json'));
  const target = links[0].target;
  assert.equal(target.package_name, 'com.vidhisangh.app');
  assert.ok(target.sha256_cert_fingerprints.every((f) => /^([0-9A-F]{2}:){31}[0-9A-F]{2}$/.test(f)));
  assert.match(read('android/app/build.gradle'), /applicationId "com\.vidhisangh\.app"/);
});

test('iOS: universal links, entitlements, privacy manifest and push are wired', async () => {
  const { APP_LINK_PREFIXES } = await import('../src/app/core/platform/app-links.ts');
  // apple-app-site-association claims the same paths as Android (plus the bare /app).
  const aasa = JSON.parse(read('public/.well-known/apple-app-site-association'));
  const detail = aasa.applinks.details[0];
  assert.match(detail.appID, /^[A-Z0-9]{10}\.com\.vidhisangh\.app$|^TEAMID\.com\.vidhisangh\.app$/);
  const claimed = detail.paths.filter((p) => p.endsWith('/*')).map((p) => p.slice(0, -1));
  assert.deepEqual(claimed.sort(), [...APP_LINK_PREFIXES].sort());
  const entitlements = read('ios/App/App/App.entitlements');
  assert.match(entitlements, /applinks:vidhisangh\.com/);
  assert.match(entitlements, /aps-environment/);
  const pbx = read('ios/App/App.xcodeproj/project.pbxproj');
  assert.match(pbx, /CODE_SIGN_ENTITLEMENTS = App\/App\.entitlements;/);
  assert.match(pbx, /PrivacyInfo\.xcprivacy in Resources/);
  assert.match(pbx, /PRODUCT_BUNDLE_IDENTIFIER = com\.vidhisangh\.app;/);
  assert.match(read('ios/App/App/PrivacyInfo.xcprivacy'), /<key>NSPrivacyTracking<\/key>\s*<false\/>/);
  const info = read('ios/App/App/Info.plist');
  assert.match(info, /NSCameraUsageDescription/);
  assert.doesNotMatch(info, /armv7/);
  const delegate = read('ios/App/App/AppDelegate.swift');
  assert.match(delegate, /Messaging\.messaging\(\)\.apnsToken = deviceToken/);
  assert.match(delegate, /capacitorDidRegisterForRemoteNotifications/);
  assert.match(delegate, /#if canImport\(FirebaseMessaging\)/, 'builds before the Firebase package is added');
  // Nothing in the iOS project may carry a Firebase config or a signing team: those come from the Mac.
  assert.equal(existsSync(join(root, 'ios/App/App/GoogleService-Info.plist')), false);
  assert.doesNotMatch(pbx, /DEVELOPMENT_TEAM = [A-Z0-9]/);
});

test('rating request: only after regular use, and not again for months', async () => {
  const { countLaunchAndDecide, MIN_LAUNCHES, GAP_DAYS } = await import('../src/app/core/platform/review-rules.ts');
  const day = 86_400_000;
  let state = null;
  let asks = 0;
  // Opened twice a day for 10 days: asked once, after day 5 and launch 8.
  for (let i = 0; i < 20; i++) {
    const r = countLaunchAndDecide(state, i * day / 2);
    state = r.state;
    if (r.ask) { asks++; assert.ok(state.launches >= MIN_LAUNCHES && i / 2 >= 5); }
  }
  assert.equal(asks, 1);
  assert.equal(countLaunchAndDecide(state, state.lastAsked + (GAP_DAYS - 1) * day).ask, false);
  assert.equal(countLaunchAndDecide(state, state.lastAsked + GAP_DAYS * day).ask, true);
});

test('live update: a fresh download (pending) is switched to; failed or half-downloaded ones are not', async () => {
  const { usableBundle } = await import('../src/app/core/platform/live-update.ts');
  const bundles = [
    { id: 'a', version: 'v1', status: 'success' },
    { id: 'b', version: 'v2', status: 'pending' },   // what download() leaves behind
    { id: 'c', version: 'v3', status: 'error' },
    { id: 'd', version: 'v4', status: 'downloading' },
  ];
  assert.equal(usableBundle(bundles, 'v2')?.id, 'b', 'regression: pending downloads were never applied (20–22 Oct 2026)');
  assert.equal(usableBundle(bundles, 'v1')?.id, 'a');
  assert.equal(usableBundle(bundles, 'v3'), undefined);
  assert.equal(usableBundle(bundles, 'v4'), undefined);
  assert.equal(usableBundle(bundles, 'v9'), undefined);
});

test('profile progress: counts the right steps per role and names the next one', async () => {
  const { profileSteps, profilePercent } = await import('../src/app/core/home/profile-progress.ts');
  const base = { headline: 'Criminal lawyer', bio: '', city: 'Delhi', practice_areas: ['Criminal'], courts: [], education: [],
    bar_council: null, year_of_enrollment: null };
  const adv = profileSteps({ ...base, professional_role: 'advocate' });
  assert.equal(adv.length, 7);
  assert.equal(adv.find((s) => !s.done)?.label, 'the courts you appear in');
  assert.equal(profilePercent(adv), 57);
  const student = profileSteps({ ...base, professional_role: 'law_student' });
  assert.ok(!student.some((s) => s.key === 'enrolment' || s.key === 'courts'));
  assert.ok(student.some((s) => s.key === 'education'));
  assert.equal(profilePercent(profileSteps({ ...base, professional_role: null, headline: null, city: null, practice_areas: [] })), 0);
});

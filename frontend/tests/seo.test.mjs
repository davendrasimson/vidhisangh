// Guards for search-engine basics: crawl rules, sitemap and per-page tags.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

const root = new URL('..', import.meta.url).pathname;
const read = (path) => readFileSync(join(root, path), 'utf8');

test('robots.txt keeps the signed-in app and private links out of search', () => {
  const robots = read('public/robots.txt');
  for (const path of ['/app/', '/api/', '/portal/', '/kyc/', '/pay/', '/esign/']) {
    assert.match(robots, new RegExp(`Disallow: ${path.replace(/\//g, '\\/')}`));
  }
  assert.match(robots, /Sitemap: https:\/\/vidhisangh\.com\/sitemap\.xml/);
});

test('sitemap lists only public, indexable pages', () => {
  const sitemap = read('public/sitemap.xml');
  assert.match(sitemap, /<loc>https:\/\/vidhisangh\.com\/<\/loc>/);
  assert.doesNotMatch(sitemap, /\/app\//);
});

test('public routes carry their own title and description', () => {
  const routes = read('src/app/app.routes.ts') + read('src/app/features/auth/auth.routes.ts');
  const seo = routes.match(/seo: \{ title:/g) ?? [];
  assert.ok(seo.length >= 7, `expected 7+ public pages with seo data, found ${seo.length}`);
});

test('index.html has structured data and no site-wide canonical', () => {
  const index = read('src/index.html');
  assert.match(index, /application\/ld\+json/);
  // A fixed canonical would mark every public page a copy of the home page.
  assert.doesNotMatch(index, /rel="canonical"/);
});

test('public pages are prerendered to static HTML in production builds', () => {
  const angular = JSON.parse(read('angular.json'));
  const build = Object.values(angular.projects)[0].architect.build.configurations;
  assert.equal(build.production.outputMode, 'static');
  assert.equal(build.mobile.server, false); // the app bundle stays client-only
  const server = read('src/app/app.routes.server.ts');
  for (const path of ["''", "'privacy'", "'terms'", "'help'", "'auth/register'"]) {
    assert.match(server, new RegExp(`path: ${path}, renderMode: RenderMode.Prerender`));
  }
});

test('bare-act pages are generated for every section of every Act', () => {
  // public/acts/ is build output (gitignored); generate it as `npm run build` does.
  execFileSync(process.execPath, [join(root, 'scripts/build-act-pages.mjs')], { cwd: root });
  const sitemap = read('public/sitemap.xml');
  const ids = readdirSync(join(root, 'content/acts')).map((f) => f.replace(/\.json$/, ''));
  assert.ok(ids.length >= 21, `expected 21+ Acts, found ${ids.length}`);
  let sections = 0, untitled = 0;
  for (const id of ids) {
    const act = JSON.parse(read(`content/acts/${id}.json`));
    assert.ok(act.title && act.short && act.source, `${id} has title, short name and source`);
    for (const sec of act.sections) {
      sections++;
      if (!sec.heading) untitled++;
      const page = read(`public/acts/${id}/section-${sec.number.toLowerCase()}/index.html`);
      assert.match(page, /<link rel="canonical" href="https:\/\/vidhisangh\.com\/acts\//);
    }
    assert.match(sitemap, new RegExp(`/acts/${id}/</loc>`));
  }
  assert.ok(untitled <= 30, `${untitled} of ${sections} sections have no heading`);
  assert.match(read('public/acts/bns/section-103/index.html'), /BNS 103\(1\)<\/b> ← <a href="\/acts\/ipc-to-bns\/section-302\/">IPC 302<\/a>/);
  assert.match(read('public/acts/ipc/section-302/index.html'), /href="\/acts\/bns\/section-103\/"/);
  assert.match(read('public/acts/ipc/section-302/index.html'), /class="repealed"/);
});

test('old law to new law: every new-law section is in the BPRD table, with a page per old section', () => {
  const sizes = { bns: 358, bnss: 531, bsa: 170 };
  for (const [id, count] of Object.entries(sizes)) {
    const table = JSON.parse(read(`content/correspondence/${id}.json`));
    const covered = new Set(table.entries.map((e) => e.new.match(/^\d+/)[0]));
    assert.equal(covered.size, count, `${id}: every section is in the table`);
    assert.ok(table.entries.every((e) => !('summary' in e)), 'the compiler\'s commentary is not copied');
  }
  const p420 = read('public/acts/ipc-to-bns/section-420/index.html');
  assert.match(p420, /<h1>IPC Section 420 is now BNS Section 318\(4\)<\/h1>/);
  assert.match(p420, /href="https:\/\/wa\.me\/\?text=IPC%20Section%20420/);
  assert.match(p420, /bprd\.mha\.gov\.in/);
  assert.match(read('public/acts/crpc-to-bnss/section-438/index.html'), /CrPC Section 438 is now BNSS Section 482/);
  assert.match(read('public/acts/evidence-to-bsa/section-65b/index.html'), /Evidence Act Section 65B is now BSA Section 63/);
  // Dropped from the new law: said plainly, without claiming more than the table does.
  assert.match(read('public/acts/ipc-to-bns/section-377/index.html'), /lists no BNS provision for IPC section 377/);
  // Amended IPC sections take the table's subject, not the outdated bundled heading.
  assert.match(read('public/acts/ipc-to-bns/section-376a/index.html'), /persistent vegetative state/);
  const index = read('public/acts/ipc-to-bns/index.html');
  assert.match(index, /<script src="\/acts\/converter\.js" defer><\/script>/);
  assert.ok((index.match(/<tr data-q=/g) ?? []).length > 500);
  assert.match(read('public/acts/converter.js'), /convert-q/);
  const sitemap = read('public/sitemap.xml');
  for (const u of ['/acts/ipc-to-bns/', '/acts/crpc-to-bnss/section-438/', '/acts/evidence-to-bsa/']) assert.ok(sitemap.includes(`https://vidhisangh.com${u}<`), u);
  assert.match(read('public/acts/index.html'), /href="\/acts\/ipc-to-bns\/"/);
});

test('the service worker leaves the static bare-act pages to the network', () => {
  const ngsw = JSON.parse(read('ngsw-config.json'));
  assert.ok(ngsw.navigationUrls.includes('!/acts/**'), 'otherwise a returning visitor gets the app shell on /acts/');
});

test('the WhatsApp number is published next to the company name (Meta display-name review)', () => {
  const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8');
  assert.match(read('src/app/core/contact.ts'), /WHATSAPP_NUMBER = '\+91 73411 00692'/);
  // The shared site footer carries it; every public page uses that footer.
  assert.match(read('src/app/shared/public-chrome/public-chrome.component.ts'), /Simson Softwares Private Limited<\/a>\.\s*WhatsApp: <a \[href\]="whatsappLink"/);
  for (const f of ['src/app/features/landing/landing.component.ts', 'src/app/features/legal/about.component.ts',
    'src/app/features/legal/legal-page.component.ts', 'src/app/features/legal/compliance-status.component.ts',
    'src/app/features/help/help-center.component.ts']) {
    assert.match(read(f), /<vs-public-footer \/>/, f);
  }
  for (const f of ['src/app/features/legal/about.component.ts', 'src/app/features/legal/legal-page.component.ts',
    'src/app/features/legal/compliance-status.component.ts', 'src/app/features/help/help-center.component.ts']) {
    assert.match(read(f), /<vs-public-header \/>/, f);
  }
  // The footer words carry data-i18n so the Hindi switch can swap them (tests/i18n.test.mjs).
  assert.match(read('scripts/build-act-pages.mjs'), /Simson Softwares Private Limited<\/a>\. <span data-i18n>WhatsApp:<\/span> <a href="https:\/\/wa\.me\/917341100692"/);
});

test('prerendered pages never carry an error toast from the build', () => {
  const src = readFileSync(new URL('../src/app/core/interceptors/error.interceptor.ts', import.meta.url), 'utf8');
  assert.match(src, /const browser = isPlatformBrowser\(inject\(PLATFORM_ID\)\)/);
  assert.match(src, /if \(browser && err\.status !== 401/);
});

test('the in-app reader uses the full old/new tables, keeping curated notes', async () => {
  const { CORRESPONDENCE, PUBLISHED_ACTS } = await import('../src/app/features/knowledge/data/correspondence-data.ts');
  const { fullCrossReferences } = await import('../src/app/features/knowledge/data/section-intelligence.ts');
  const ipc420 = fullCrossReferences(CORRESPONDENCE, 'ipc', '420');
  assert.deepEqual(ipc420.map((r) => `${r.correspondingActId} ${r.correspondingSection}`), ['bns 318(4)']);
  const bns318 = fullCrossReferences(CORRESPONDENCE, 'bns', '318');
  assert.deepEqual(bns318.map((r) => r.correspondingSection).sort(), ['415', '417', '418', '420']);
  // Not among the curated 32, now found:
  assert.equal(fullCrossReferences(CORRESPONDENCE, 'crpc', '125')[0]?.correspondingSection, '144');
  // The curated note on IPC 304A survives.
  assert.match(fullCrossReferences(CORRESPONDENCE, 'ipc', '304A')[0].note ?? '', /106\(2\)/);
  assert.ok(PUBLISHED_ACTS.includes('bns') && !PUBLISHED_ACTS.includes('crpc'));
});

test('section pages offer save / judgments / discuss, each a sign-up that lands on it', async () => {
  const html = read('public/acts/bns/section-103/index.html');
  assert.match(html, /<aside class="section-actions">/);
  assert.match(html, /returnUrl=%2Fapp%2Fknowledge%2Freader%3Fact%3Dbns%26section%3D103/);
  assert.match(html, /returnUrl=%2Fapp%2Fresearch%3Fact%3DBharatiya%2520Nyaya%2520Sanhita%26section%3D103/);
  const { safeNext } = await import('../src/app/core/navigation/after-signup.ts');
  assert.equal(safeNext('/app/research?act=Penal%20Code&section=420'), '/app/research?act=Penal%20Code&section=420');
  for (const bad of ['https://evil.example/app/x', '//evil.example', '/auth/login', '/app\\x', 'javascript:alert(1)']) assert.equal(safeNext(bad), null, bad);
});

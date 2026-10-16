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
  assert.match(read('public/acts/bns/section-103/index.html'), /Indian Penal Code, 1860 \(IPC\), section 302/);
  assert.match(read('public/acts/ipc/section-302/index.html'), /href="\/acts\/bns\/section-103\/"/);
  assert.match(read('public/acts/ipc/section-302/index.html'), /class="repealed"/);
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
  assert.match(read('scripts/build-act-pages.mjs'), /Simson Softwares Private Limited<\/a>\. WhatsApp: <a href="https:\/\/wa\.me\/917341100692"/);
});

test('prerendered pages never carry an error toast from the build', () => {
  const src = readFileSync(new URL('../src/app/core/interceptors/error.interceptor.ts', import.meta.url), 'utf8');
  assert.match(src, /const browser = isPlatformBrowser\(inject\(PLATFORM_ID\)\)/);
  assert.match(src, /if \(browser && err\.status !== 401/);
});

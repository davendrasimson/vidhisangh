// Guards for search-engine basics: crawl rules, sitemap and per-page tags.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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

test('bare-act pages exist for every section and are in the sitemap', () => {
  const sitemap = read('public/sitemap.xml');
  for (const id of ['bns', 'bnss', 'bsa']) {
    const act = JSON.parse(read(`content/acts/${id}.json`));
    assert.ok(act.sections.length > 100, `${id} has sections`);
    for (const sec of act.sections) {
      assert.ok(sec.heading, `${id} ${sec.number} has a heading`);
      const page = read(`public/acts/${id}/section-${sec.number.toLowerCase()}/index.html`);
      assert.match(page, /<link rel="canonical" href="https:\/\/vidhisangh\.com\/acts\//);
    }
    assert.match(sitemap, new RegExp(`/acts/${id}/section-1/</loc>`));
  }
  assert.match(read('public/acts/bns/section-103/index.html'), /Indian Penal Code, 1860 \(IPC\), section 302/);
});

test('the service worker leaves the static bare-act pages to the network', () => {
  const ngsw = JSON.parse(read('ngsw-config.json'));
  assert.ok(ngsw.navigationUrls.includes('!/acts/**'), 'otherwise a returning visitor gets the app shell on /acts/');
});

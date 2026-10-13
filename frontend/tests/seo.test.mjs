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

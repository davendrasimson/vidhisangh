import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { HELP_TOPICS, topicForUrl } from '../src/app/features/help/help-content.ts';

test('every routable workspace and public page has a specific help article', () => {
  const routes = readFileSync(new URL('../src/app/app.routes.ts', import.meta.url), 'utf8');
  const split = routes.indexOf('children: [');
  for (const match of routes.matchAll(/path: '([^']+)'/g)) {
    const path = match[1];
    if (['auth', 'app', '**'].includes(path)) continue;
    const url = (match.index > split ? '/app/' : '/') + path.replace(/:[^/]+/g, 'example');
    const article = topicForUrl(url);
    assert.ok(article, url);
    if (!url.endsWith('/help')) assert.notEqual(article.id, 'help', `Missing article: ${url}`);
  }
  const auth = readFileSync(new URL('../src/app/features/auth/auth.routes.ts', import.meta.url), 'utf8');
  for (const match of auth.matchAll(/path: '([^']+)'/g)) {
    assert.notEqual(topicForUrl('/auth/' + match[1].replace(/:[^/]+/g, 'example')).id, 'help');
  }
});

test('nested routes, view selectors and trailing slashes resolve correctly', () => {
  for (const [url, id] of [
    ['/app/matters/42/portal', 'matter-portal'], ['/app/matters/42', 'matter-detail'],
    ['/app/documents/drafts/42', 'draft-editor'], ['/app/research/case/123', 'case'],
    ['/app/research/123', 'judgment'], ['/app/knowledge/reader?act=ipc', 'act-reader'],
    ['/app/knowledge?view=acts&q=contract', 'bare-acts'], ['/app/knowledge?view=firm', 'knowledge'],
    ['/app/billing?section=timesheets', 'timesheets'], ['/app/billing/123', 'invoice-detail'],
    ['/app/documents/?secret=private#section', 'documents'], ['/help?topic=matters', 'help'],
    ['/app/matters-other', 'help'],
  ]) assert.equal(topicForUrl(url).id, id, url);
});

test('public tokens and record IDs never become help content', () => {
  for (const url of ['/esign/SECRET_TOKEN?email=private@example.com', '/portal/SECRET_TOKEN', '/app/matters/SECRET_TOKEN']) {
    assert.ok(!JSON.stringify(topicForUrl(url)).includes('SECRET_TOKEN'));
    assert.ok(!JSON.stringify(topicForUrl(url)).includes('private@example.com'));
  }
});

test('articles are complete and unique, with prominent features and actionable hidden features', () => {
  assert.equal(new Set(HELP_TOPICS.map(t => t.id)).size, HELP_TOPICS.length);
  for (const topic of HELP_TOPICS) {
    assert.ok(topic.title && topic.summary && topic.tip && topic.steps.length, topic.id);
  }
  for (const id of ['matters', 'documents', 'calendar', 'crm', 'clients', 'billing', 'timesheets', 'payments', 'research', 'bare-acts', 'knowledge', 'network', 'people', 'groups', 'messages', 'news', 'marketplace', 'analytics', 'profile', 'settings']) {
    assert.equal(HELP_TOPICS.find(t => t.id === id)?.featured, true, id);
  }
  assert.match(topicForUrl('/app/matters').steps.join(' '), /Configure additional matter fields/);
  assert.match(topicForUrl('/app/documents').steps.join(' '), /Prepare for e-signature/);
});

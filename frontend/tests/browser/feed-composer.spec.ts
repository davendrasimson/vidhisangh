import { expect, test } from '@playwright/test';

const USER = { id: 'u1', tenant_id: 't', email: 'adv@example.com', full_name: 'Adv. Writer', is_active: true,
  is_email_verified: true, roles: [], permissions: [], mfa_enabled: false };
// 1x1 white PNG
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC', 'base64');

test('rich composer: grows with a pasted article, formats text, posts photos', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vs.session', '1'));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidTEiLCAidGlkIjogInQiLCAiZXhwIjogOTk5OTk5OTk5OSwgInNjb3BlcyI6IFsiKiJdfQ.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 } }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  await page.route('**/api/v1/network/feed**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/network/post-images', r => r.fulfill({ status: 201, json: { id: 'img-1', width: 1, height: 1 } }));
  await page.route('**/api/v1/network/post-images/img-1', r => r.fulfill({ body: PNG, contentType: 'image/png' }));
  let sent: Record<string, unknown> | undefined;
  await page.route('**/api/v1/network/posts', async r => {
    sent = r.request().postDataJSON();
    await r.fulfill({ status: 201, json: {
      id: 'p1', author_id: 'u1', author_name: 'Adv. Writer', author_headline: null, author_avatar_url: null,
      post_type: 'text', title: null, content: 'x', content_html: sent!['content_html'], images: [{ id: 'img-1', width: 1, height: 1 }],
      visibility: 'public', hashtags: [], like_count: 0, comment_count: 0, share_count: 0, created_at: new Date().toISOString(),
      link_url: null, link_title: null, link_description: null, link_image: null, link_site_name: null,
      my_reaction: null, bookmarked: false, shared_from_id: null, shared_author_name: null, shared_author_avatar_url: null,
      shared_content: null, shared_created_at: null, mentions: [] } });
  });
  await page.goto('/app/network');
  const editor = page.getByRole('textbox', { name: 'Write a post' });
  await expect(editor).toBeVisible();
  const before = (await editor.boundingBox())!.height;

  // Paste a long article: the box grows instead of scrolling a two-line textarea.
  const article = Array.from({ length: 12 }, (_, i) => 'Paragraph ' + (i + 1) + ' of the article about BNS, BNSS and BSA.').join('\n\n');
  await editor.click();
  await page.evaluate(text => {
    const dt = new DataTransfer(); dt.setData('text/plain', text);
    document.querySelector('.ProseMirror')!.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
  }, article);
  await expect(editor).toContainText('Paragraph 12');
  expect((await editor.boundingBox())!.height).toBeGreaterThan(before * 3);

  // Bold, then a photo.
  await page.keyboard.press('ControlOrMeta+a');
  await page.getByRole('button', { name: 'Bold' }).click();
  await page.locator('input[type=file]').setInputFiles({ name: 'p.png', mimeType: 'image/png', buffer: PNG });
  await expect(page.getByAltText('Photo to post')).toBeVisible();
  const post = page.getByRole('button', { name: /^send Post$|Post$/ });
  await expect(post).toBeEnabled();
  await post.click();

  await expect.poll(() => sent).toBeTruthy();
  expect(String(sent!['content_html'])).toContain('<strong>Paragraph 1 of the article');
  expect(sent!['image_ids']).toEqual(['img-1']);
  expect(String(sent!['content'])).toContain('Paragraph 12');
  // Published post shows the formatting and the photo; the composer is empty again.
  await expect(page.locator('.vs-post-body strong').first()).toContainText('Paragraph 1');
  await expect(page.getByAltText('Photo in the post')).toBeVisible();
  await expect(editor).not.toContainText('Paragraph');
});

test('official VidhiSangh posts show the logo, an Official mark and the link card', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vs.session', '1'));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidTEiLCAidGlkIjogInQiLCAiZXhwIjogOTk5OTk5OTk5OSwgInNjb3BlcyI6IFsiKiJdfQ.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 } }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  const base = { author_avatar_url: null, images: [], visibility: 'public', like_count: 0, comment_count: 0, share_count: 0,
    created_at: new Date().toISOString(), link_description: null, link_image: null, my_reaction: null, bookmarked: false,
    shared_from_id: null, shared_author_name: null, shared_author_avatar_url: null, shared_content: null, shared_created_at: null, mentions: [] };
  await page.route('**/api/v1/network/feed**', r => r.fulfill({ json: [
    { ...base, id: 'o1', author_id: '5e1d0f00-7a1d-4e5a-9c0b-000000000001', author_name: 'VidhiSangh',
      author_headline: 'Official · Section of the day, Supreme Court judgments and legal news', post_type: 'announcement',
      title: 'Section of the day', content: 'Section of the day: BNS 318 — Cheating',
      content_html: '<p><strong>Section of the day: BNS 318 — Cheating</strong></p><p>Earlier: IPC 415, 417, 418, 420.</p>',
      hashtags: ['SectionOfTheDay', 'BNS'], link_url: 'https://vidhisangh.com/acts/bns/section-318/',
      link_title: 'Section 318 BNS — Cheating', link_site_name: 'VidhiSangh Bare Acts' },
    { ...base, id: 'p2', author_id: 'u9', author_name: 'Adv. Member', author_headline: null, post_type: 'text', title: null,
      content: 'Hello', content_html: '<p>Hello</p>', hashtags: [], link_url: null, link_title: null, link_site_name: null },
  ] }));
  await page.goto('/app/network');
  const official = page.locator('article', { hasText: 'Section of the day: BNS 318' });
  await expect(official.getByText('Official', { exact: true })).toBeVisible();
  await expect(official.locator('img[src="/brand-mark.svg"]')).toBeVisible();
  await expect(official.getByText('Section 318 BNS — Cheating')).toBeVisible();
  const member = page.locator('article', { hasText: 'Adv. Member' });
  await expect(member.getByText('Official', { exact: true })).toHaveCount(0);
  await expect(member.getByText('AM', { exact: true })).toBeVisible();
});

test('photos open full screen: next, previous, Esc; a repost shows the original photos', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vs.session', '1'));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidTEiLCAidGlkIjogInQiLCAiZXhwIjogOTk5OTk5OTk5OSwgInNjb3BlcyI6IFsiKiJdfQ.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 } }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  await page.route('**/api/v1/network/post-images/**', r => r.fulfill({ body: PNG, contentType: 'image/png' }));
  const base = { author_avatar_url: null, visibility: 'public', like_count: 0, comment_count: 0, share_count: 0, created_at: new Date().toISOString(),
    link_url: null, link_title: null, link_description: null, link_image: null, link_site_name: null, my_reaction: null, bookmarked: false,
    shared_author_avatar_url: null, shared_created_at: null, mentions: [], hashtags: [], post_type: 'text', title: null, content_html: null, author_headline: null };
  await page.route('**/api/v1/network/feed**', r => r.fulfill({ json: [
    { ...base, id: 'p1', author_id: 'u9', author_name: 'Adv. Photo', content: 'Two photos', images: [{ id: 'i1', width: 1, height: 1 }, { id: 'i2', width: 1, height: 1 }],
      shared_from_id: null, shared_author_name: null, shared_content: null },
    { ...base, id: 'p2', author_id: 'u8', author_name: 'Adv. Sharer', content: 'Congratulations!', images: [],
      shared_from_id: 'p0', shared_author_name: 'Adv. Origin', shared_content: 'Election day', shared_images: [{ id: 'i3', width: 1, height: 1 }] },
  ] }));
  await page.goto('/app/network');
  await page.getByRole('button', { name: 'Open photo 1 of 2' }).click();
  const viewer = page.getByRole('dialog', { name: 'Photo viewer' });
  await expect(viewer.getByText('1 of 2')).toBeVisible();
  await viewer.getByRole('button', { name: 'Next photo' }).click();
  await expect(viewer.getByText('2 of 2')).toBeVisible();
  await expect(viewer.getByRole('button', { name: 'Next photo' })).toBeDisabled();
  await page.keyboard.press('ArrowLeft');
  await expect(viewer.getByText('1 of 2')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(viewer).toHaveCount(0);

  await page.locator('article', { hasText: 'Election day' }).getByRole('button', { name: 'Open photo 1 of 1' }).click();
  await expect(page.getByRole('dialog', { name: 'Photo viewer' }).getByRole('img', { name: 'Photo 1 of 1' })).toBeVisible();
  await page.getByRole('button', { name: 'Close photo viewer' }).click();
  await expect(page.getByRole('dialog', { name: 'Photo viewer' })).toHaveCount(0);
});

test('group posts use the formatting composer and show photos', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vs.session', '1'));
  await page.route('**/api/v1/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', r => r.fulfill({ json: { access_token: 'eyJhbGciOiAiSFMyNTYifQ.eyJzdWIiOiAidTEiLCAidGlkIjogInQiLCAiZXhwIjogOTk5OTk5OTk5OSwgInNjb3BlcyI6IFsiKiJdfQ.sig', refresh_token: null, token_type: 'bearer', expires_in: 900 } }));
  await page.route('**/api/v1/auth/me', r => r.fulfill({ json: USER }));
  const GID = '22222222-2222-4222-8222-222222222222';
  await page.route(`**/api/v1/groups/${GID}`, r => r.fulfill({ json: {
    id: GID, slug: 'bail', name: 'Bail Practice', description: null, group_type: 'community', visibility: 'public', avatar_url: null, cover_url: null,
    owner_id: 'u1', tenant_id: null, is_verified: false, member_count: 3, post_count: 0, created_at: new Date().toISOString(), my_role: 'member', my_status: 'active' } }));
  await page.route('**/api/v1/network/post-images', r => r.fulfill({ status: 201, json: { id: 'img-g1', width: 1, height: 1 } }));
  await page.route('**/api/v1/network/post-images/img-g1', r => r.fulfill({ body: PNG, contentType: 'image/png' }));
  let sent: Record<string, unknown> | undefined;
  await page.route(`**/api/v1/groups/${GID}/posts**`, async r => {
    if (r.request().method() !== 'POST') return r.fulfill({ json: [] });
    sent = r.request().postDataJSON();
    await r.fulfill({ status: 201, json: { id: 'gp1', group_id: GID, author_id: 'u1', author_name: 'Adv. Writer', author_avatar_url: null,
      content: 'Default bail', content_html: sent!['content_html'], images: [{ id: 'img-g1', width: 1, height: 1 }],
      like_count: 0, comment_count: 0, created_at: new Date().toISOString(), liked: false } });
  });
  await page.goto(`/app/groups/${GID}`);
  const editor = page.getByRole('textbox', { name: 'Write a post' });
  await editor.click();
  await page.keyboard.type('Default bail');
  await page.keyboard.press('ControlOrMeta+a');
  await page.getByRole('button', { name: 'Bold' }).click();
  await page.locator('input[type=file]').setInputFiles({ name: 'p.png', mimeType: 'image/png', buffer: PNG });
  await expect(page.getByAltText('Photo to post')).toBeVisible();
  await page.getByRole('button', { name: 'Post', exact: true }).click();
  await expect.poll(() => sent?.['image_ids']).toEqual(['img-g1']);
  expect(String(sent?.['content_html'])).toContain('<strong>Default bail</strong>');
  await expect(page.locator('article strong', { hasText: 'Default bail' })).toBeVisible();
  await page.getByRole('button', { name: 'Open photo 1 of 1' }).click();
  await expect(page.getByRole('dialog', { name: 'Photo viewer' })).toBeVisible();
});

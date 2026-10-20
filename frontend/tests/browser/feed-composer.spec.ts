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

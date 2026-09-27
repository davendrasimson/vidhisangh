# Official legal news

LiveLaw is excluded from list and detail APIs, rejected by the RSS importer, and its 55 old articles were reversibly archived on 25 September 2026. Production VS_NEWS_FEEDS remains [].

Run `python -m app.scripts.ingest_official_news --dry-run` to preview dated Supreme Court judgment listings from https://www.sci.gov.in/. Without --dry-run it imports at most 50 listings per run, deduplicated by official document URL. One bounded homepage request is made; article text is not crawled and legal holdings are not inferred. Failed requests or empty parses preserve existing data. The public homepage is permitted by the official robots policy. Standard HTTPX requests work; the custom bot user agent received HTTP 403.

`--archive-competitor` reversibly sets deleted_at on competitor articles in the same transaction as a successful official import. The timer/service files in infra/jobs/vidhisangh-official-news.* refresh hourly. Monitor with `journalctl -u vidhisangh-official-news.service`.

Current coverage is Supreme Court judgment publication notices, not comprehensive legal reporting. Additional official sources need verified adapters.

Image storage uses migration 0042_news_images. Verify the actual column before deploying the model. Migrations use .env.admin, not the runtime account. Cards display locally hosted editorial artwork and label it as an AI illustration, not an event photograph. This is shared court-themed artwork, not a unique depiction of each case.

Asset: frontend/public/images/news/justice-editorial.png
Generated with the built-in imagegen tool.
Final prompt: Create a polished editorial illustration for an Indian legal news website. Landscape 1536x1024. A dignified Indian domed courthouse in warm sandstone, an open law book in foreground and balanced brass scales of justice, leafy trees and soft daylight. Rich textured painted editorial style, navy blue and sandstone gold palette, detailed architectural scene, spacious composition suited to a news card crop. No people, no words, no logos, no watermarks. This is clearly an illustrative depiction, not a photograph of an actual case or event.

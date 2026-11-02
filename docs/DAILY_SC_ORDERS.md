# Daily Supreme Court orders and subscriber email

The daily workflow retrieves newly listed official Supreme Court orders, extracts complete PDF text, exports it for the existing **no-paid-API** headnote-writing process, and emails opted-in members after validated headnotes have been imported. It never invokes a model or paid API. The subscriber setting is under **Settings → Notifications → Supreme Court order emails**.

Implementation: `app.scripts.daily_sc_orders.run`, with intake/export/delivery functions in `app.modules.research.daily_orders`. Migration `0088_sc_daily_orders` adds intake provenance, subscriptions and durable send claims. Existing `Judgment` and `AiHeadnoteContent` remain the source of headnote content.

## Operation

From `backend`, with the normal application environment:

```bash
# Read-only discovery preview: no database writes, export files or email.
python -m app.scripts.daily_sc_orders

# Retrieve PDFs and queue their complete text for offline writing.
VS_SC_DAILY_ENABLED=true python -m app.scripts.daily_sc_orders --execute \
  --export-pending /tmp/daily-sc-headnotes
```

`queue.json` is the authoritative manifest of orders still needing headnotes. Each `<id>.txt` includes the complete extracted source, official link and downloaded PDF checksum. Previous files are preserved for provenance even when their IDs disappear from the current manifest. Read the complete source and actual applicable clauses, and write original paragraph-grounded headnotes using the existing `AiHeadnoteContent` schema. Produce JSONL records of the form `{"id":"...","headnote":{...}}`. These are compatible with the existing importer:

```bash
python -m app.scripts.ai_headnotes import --file /tmp/daily-results.jsonl \
  --model <actual-writing-model> --dry-run
python -m app.scripts.ai_headnotes import --file /tmp/daily-results.jsonl \
  --model <actual-writing-model>

# Deliver imported headnotes without requiring a fresh successful SCI fetch.
VS_SC_DAILY_ENABLED=true python -m app.scripts.daily_sc_orders --execute --send-only
```

Existing headnotes are never overwritten. Unreadable/scanned PDFs go to `needs_review` rather than generating a headnote from partial text. Network failures remain retryable. `sc_daily_orders` records status, safe error categories, first discovery and PDF SHA-256. Retrieval/extraction processes up to 100 pending records per run, prioritising missing text. Run intake again to drain a larger backlog; all discovered entries are registered first. No source text is silently truncated.

## Email behaviour

Only active accounts with verified email and an explicit daily-orders subscription qualify. General Email-off preferences also pause the digest. This does not enrol all accounts or outreach contacts. Subscriptions start from their opt-in time; the historical research corpus is not emailed. Newly discovered orders with an older decision date can still qualify, and the actual order date is displayed.

A digest includes up to 25 previously unclaimed orders with imported headnotes: case title, order date, AI label, summary, result, held points and source paragraph references, a public headnote link, and the official document link. Additional ready orders wait for subsequent digests. Orders awaiting headnotes are not marked delivered, and are picked up after import. No empty digest is sent.

The SMTP provider sends both plain text and HTML with one-click unsubscribe headers. GET of the unsubscribe link only shows confirmation; POST withdraws the subscription, so link-scanning software does not unsubscribe members. Resubscribing rotates the token. The API exposes only the caller's own subscription.

`sc_daily_emails` claims each member/day before SMTP, under a unique database constraint. A PostgreSQL advisory lock also prevents overlapping CLI jobs. `sent` means SMTP accepted the message, not that the recipient read it. `sending` after a crash, or `uncertain` after an SMTP exception, is **not automatically retried**: inspect the mail server's delivery records before manually reconciling the claim. Those order IDs stay excluded from later digests to prevent duplicates after ambiguous acceptance. An uncertain send or retryable PDF retrieval failure exits nonzero for the systemd failure alert.

## WhatsApp digest (2 Nov 2026)

After the email digest, the same run sends the **WhatsApp digest** (`app.modules.research.daily_whatsapp.send_whatsapp_digests`), Meta-approved MARKETING template `sc_daily_orders` in `en` (id 1657367549377686) and `hi` (id 1021228031043552) on +91 73411 00692. Five body parameters: first name, number of orders, date, leading case (the first order of the member's email digest, folded to one line, ≤120 chars), its headnote's result (≤150 chars); static buttons "Read today's headnotes" (`/judgments/`) and "Open the app". Hindi when the profile lists Hindi but not English.

Who gets it: members whose **email digest for that IST day was sent** (so both channels describe the same orders), with an enabled subscription, a verified number and a **"yes" to WhatsApp updates** (the consent ledger; "no" or "not asked" means no message). One per member per day, claimed in `whatsapp_campaign_sends` under campaign `sc-daily-<date>` before the API call; a failed send is recorded and not retried that day. The report in the job's JSON output is `whatsapp: {sent, already, failed, eligible, no_consent, no_number}`; `whatsapp_skipped` means the unit lacks the number's token.

Timing: the 17:30 and 19:30 IST runs fetch, export and deliver whatever is ready; a second unit, `vidhisangh-sc-daily-send.{service,timer}` at **21:00 IST**, runs `--execute --send-only` so headnotes imported in the ninety minutes between go out the same evening. A manual `--send-only` after a later import delivers at once (both channels). Both units load the `wa_access_token` credential and set `VS_WA_PHONE_NUMBER_ID`. Tests: `tests/test_daily_sc_whatsapp.py`.

## Enable the daily schedule

Production deployment completed on 2 November 2026. Revision `0088_sc_daily_orders` is applied, the API and production frontend are deployed, and the timer is enabled. The first service run exited successfully with zero discovered orders and zero emails. No launch email was sent. For future installations:

1. Deploy the backend/frontend and apply `alembic upgrade head` (revision 0088).
2. Set `VS_SC_DAILY_ENABLED=true`, `VS_PUBLIC_APP_URL`, and the existing `VS_SMTP_*` configuration. No AI API credentials are needed.
3. Make `/opt/vidhisangh/backups` writable by the `ubuntu` service user. The service exports to `backups/orders/daily-sc-headnotes` and loads the existing encrypted SMTP credential from `/etc/credstore.encrypted/vidhisangh.smtp_password`.
4. Install `infra/jobs/vidhisangh-sc-daily.{service,timer}` and `vidhisangh-sc-daily-send.{service,timer}` in `/etc/systemd/system`, reload systemd, then enable/start both timers.

The supplied timer runs twice daily, at **17:30 and 19:30 Asia/Kolkata** (once at 20:30 until 2 Nov 2026), including catch-up after downtime. It retrieves, exports the pending queue, and delivers headnotes already imported. Writing/import is still the established offline step chosen by the owner; unattended headnote generation is not enabled. Use `--send-only` after an import when delivery is needed before the next scheduled run. Each member still receives at most one digest per IST day.

## Source coverage and verification

Discovery reads the official [latest orders](https://www.sci.gov.in/latest-orders/) and [homepage judgment/order links](https://www.sci.gov.in/). These are rolling public listings, **not a guaranteed complete date-range archive**. There is no CAPTCHA bypass or unofficial mirror. Late publications are discovered while present in the listings; long outages can require manual reconciliation against the Court's daily-order service.

Only allowlisted official HTTPS document hosts are fetched, including every redirect. Responses and PDF page counts are bounded. Changed/unrecognised listing markup fails instead of being silently treated as an empty day. Explicit “No records found” is reported as zero discovered, not a certification that the Court passed no orders. On 2 November 2026 the live latest-orders page returned that explicit empty state, so populated listing/PDF behaviour was tested with fixtures; live full-day completeness is not claimed.

Tests cover official URL restrictions, redirect checks, listing dates and empty/broken pages, PDF wrappers, duplicate intake, complete offline export/import, unreadable/retryable PDFs, subscription eligibility, opt-out/token rotation, email content escaping, late headnote availability and duplicate/ambiguous-send protection. All test email delivery uses a recorder.

Validation completed on 2 November 2026: 17 workflow tests passed; existing headnote-import and notification regression tests passed; Angular development build and TypeScript checks passed; Alembic generated revision 0088 PostgreSQL SQL successfully. Production migration and scheduler activation were subsequently completed. Live API health, database readiness, subscription authentication and the deployed frontend bundle were verified. The initial production run reported no retrieval failures, zero discovered orders and zero emails; there are currently no daily-order subscriptions. Live subscriber delivery has not been exercised.

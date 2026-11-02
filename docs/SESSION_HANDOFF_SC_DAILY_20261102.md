# Session handoff: daily Supreme Court orders

Recorded 2 November 2026 after production deployment. Read this together with `docs/DAILY_SC_ORDERS.md` for the full operator workflow.

## User request and decisions

The user requested daily Supreme Court order retrieval, headnote writing and subscriber email, then explicitly authorized deployment and setup on the existing server. They selected **the existing no-paid-API workflow**. Consequently, intake, text export and delivery are scheduled; headnote writing/import remains an offline operator/session step. No unattended headnote writer or paid model API was added. Do not describe the whole writing process as autonomous.

## What is deployed

Production SSH alias: `vidhisangh`; application root `/opt/vidhisangh`; application user `ubuntu`. The backend is in `backend`, virtual environment `.venv`. This server deployment is not a Git checkout.

- Revision `0088_sc_daily_orders` applied after `0087_outreach_engagement`. Adds `sc_daily_orders`, `sc_daily_subscriptions`, `sc_daily_emails`.
- Backend deployed and `vidhisangh-api` gracefully reloaded.
- Production frontend built with `npm run build` and deployed using rsync without deletion to retain older hashed assets. Verified live main bundle `main-KEX2SJNI.js`.
- `VS_SC_DAILY_ENABLED=true` set in the server backend `.env`.
- Installed and enabled `vidhisangh-sc-daily.service` and `.timer`. Runs daily at **20:30 Asia/Kolkata**, with up to 120 seconds jitter and persistent catch-up.
- Service uses the existing encrypted SMTP credential `/etc/credstore.encrypted/vidhisangh.smtp_password`. SMTP host configuration was confirmed; credentials were not changed.
- Export location: `/opt/vidhisangh/backups/orders/daily-sc-headnotes`.
- Members subscribe through **Settings → Notifications → Supreme Court order emails**.

The first live run at 16:22 UTC on 2 November completed with exit status 0: discovered 0, added 0, ready 0, pending headnotes 0, retrieval failures 0, exported 0, sent 0, eligible 0. All three new tables were empty and `queue.json` was `[]`. This is an empty listing result, not proof the Court issued no orders that day. No launch email was sent and actual subscriber delivery has not been tested.

Live checks passed: `/health`, backend `/ready` (database and Redis), migration revision, app-user access to the three tables, new subscription endpoint returning 401 without authentication, and production frontend bundle. For a direct readiness request use the expected Host header:

```bash
ssh vidhisangh 'curl -fsS -H "Host: vidhisangh.com" http://127.0.0.1:8000/ready'
```

## How it works

- `backend/app/modules/research/daily_source.py`: discovers rolling official links from `https://www.sci.gov.in/latest-orders/` and the SCI homepage; resolves official PDF wrappers, checks allowlisted HTTPS hosts and every redirect, extracts complete PDF text. Scanned/unreadable documents require review. No CAPTCHA bypass.
- `daily_models.py`: intake provenance/status, explicit subscriptions with rotating unsubscribe tokens, durable email claims.
- `daily_orders.py`: deduplicates intake, extracts text, exports pending records, selects validated imported headnotes, builds plain/HTML digests and claims deliveries before SMTP.
- `daily_router.py`: unsubscribe confirmation GET and mutation POST, avoiding accidental unsubscribe by link scanners.
- `backend/app/scripts/daily_sc_orders.py`: read-only preview by default; explicit execution/export/send flags; PostgreSQL advisory lock prevents concurrent job runs.
- `backend/app/modules/notifications/router.py`: caller-own GET/PUT daily subscription API. Frontend notification service/settings expose the toggle.
- `backend/app/core/channels.py`: HTML alternative and unsubscribe headers.
- Systemd definitions: `infra/jobs/vidhisangh-sc-daily.{service,timer}`.

Only active, verified-email users who explicitly opt in qualify; general Email-off also pauses delivery. Only records discovered after opt-in qualify. Digests require imported, schema-valid headnotes and provenance; no empty emails. Maximum 25 orders per subscriber per IST day, with remaining ready orders waiting. Durable claims prevent duplicate delivery. SMTP failures with uncertain acceptance are not automatically resent: reconcile with mail logs before any manual recovery.

## Continue daily headnote work

Inspect the authoritative exported `queue.json`; previous text files are retained as provenance even when removed from the pending manifest. Read each complete source before writing original, paragraph-grounded headnotes using the existing `AiHeadnoteContent` schema. No invented holdings or summaries based only on titles. Export records as JSONL `{"id":"...","headnote":{...}}` and use the existing importer, without force:

```bash
# Run on server from /opt/vidhisangh/backend with its normal environment loaded.
set -a
. ./.env
set +a
export PYTHONPATH="$PWD"
.venv/bin/python -m app.scripts.ai_headnotes import --file /tmp/daily-results.jsonl --model <actual-writing-model> --dry-run
.venv/bin/python -m app.scripts.ai_headnotes import --file /tmp/daily-results.jsonl --model <actual-writing-model>
.venv/bin/python -m app.scripts.daily_sc_orders --execute --send-only
```

Use the actual writing model identifier, validate import results and exact readback as in the established headnote workflow. Never replace existing headnotes by default. `--send-only` delivers ready records without depending on another successful SCI fetch; daily eligibility and duplicate protections still apply.

Operational checks:

```bash
ssh vidhisangh 'sudo systemctl list-timers vidhisangh-sc-daily.timer --no-pager'
ssh vidhisangh 'sudo journalctl -u vidhisangh-sc-daily.service -n 40 --no-pager'
ssh vidhisangh 'cat /opt/vidhisangh/backups/orders/daily-sc-headnotes/queue.json'
# Explicitly run the installed workflow when needed:
ssh vidhisangh 'sudo systemctl start vidhisangh-sc-daily.service'
```

Intake processes up to 100 pending extractions per run; repeated runs drain larger backlogs. Official listings are rolling feeds, **not guaranteed complete date archives**. Long outages or missing publications need reconciliation with the Court's order service. Explicit “No records found” is accepted as an empty listing; unrecognised markup fails closed.

## Validation and deployment precautions

17 new workflow tests passed, plus existing headnote-import/notification regression tests. Ruff, TypeScript, Angular development and production builds, offline PostgreSQL migration generation, and diff whitespace checks passed. Email tests use a recorder; production subscriber SMTP delivery remains unexercised.

Deployment used a selective 14-file backend/migration/unit/operator-doc package, not a full backend overwrite. Existing modified backend files matched their Git HEAD base hashes before deployment. The first tar extraction hit root-owned `infra/jobs`; those two units were then extracted with sudo, and migration/install completed successfully. Previous code and backend environment were saved under `/opt/vidhisangh/backups/sc-daily-deploy-<UTC timestamp>/`; environment backup permissions are 0600. Do not print environment files or service drop-ins containing credentials.

For future migrations, load **`.env.admin`** before Alembic; normal jobs use **`.env`**. Backend code changes use graceful API reload. Environment/credential changes affecting API workers require restart. Keep frontend hashed assets: do not use rsync `--delete` on frontend deployment. Local pytest needs escalation in this environment because sandboxed SQLite async threads stall.

## Local workspace and previous work

No Git commit was made. Feature code/tests/docs and frontend changes remain in the shared workspace. Preserve unrelated edits in `docs/AI_HEADNOTES.md`, `docs/HEADNOTE_PRIMARY_20261027_2000.md`, and untracked `.claude/`. Do not blindly reset or deploy the entire dirty tree.

Earlier session context reports the reserved 2,000 headnotes completed, imported and verified. The recorded wider Supreme Court figures were 7,366 completed and 31,000 pending; these are historical context, **not refreshed during this deployment**. Do not present them as current without querying the server.

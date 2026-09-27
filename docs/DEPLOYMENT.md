# Production deployment — vidhisangh.com

Live at **https://vidhisangh.com** (and `www`). Single host, `203.193.166.109`,
Ubuntu 24.04. This file is the record of how it is wired; keep it current.

## Access

```
ssh vidhisangh          # ~/.ssh/config alias → ubuntu@203.193.166.109
                        # key: ~/.ssh/id_ed25519_vidhisangh (no passphrase)
```

Password auth still works on the server. Once you are happy with key access,
consider `PasswordAuthentication no` in `/etc/ssh/sshd_config`.

## Layout

| Thing | Where |
|---|---|
| Code | `/opt/vidhisangh/{backend,frontend}` |
| Secrets | `/opt/vidhisangh/.secrets/` (0700; DB passwords, JWT keys) |
| App env | `/opt/vidhisangh/backend/.env` (app role, 0600) |
| Migration env | `/opt/vidhisangh/backend/.env.admin` (owner role, 0600) |
| API service | `systemd: vidhisangh-api` → gunicorn/uvicorn, 3 workers, `127.0.0.1:8000` |
| Web | nginx → SPA from `frontend/dist/vidhisangh/browser`, `/api/v1/` proxied |
| DNS | BIND9, zone `/etc/bind/db.vidhisangh.com` |

## DNS — we are our own registrar-delegated nameserver

The `.com` registry holds glue for **ns1** and **ns2**, both → `203.193.166.109`,
so this box *is* the authoritative nameserver for the domain.

BIND is **authoritative-only**: `recursion no` + `allow-recursion { none; }`, so it
cannot be abused as an open resolver for amplification attacks. It binds the two
real interfaces, never loopback, so `systemd-resolved` still answers for the host
itself. Verify with `dig @203.193.166.109 google.com` → must be `REFUSED`.

**Bump the SOA serial on every zone edit**, then `sudo rndc reload vidhisangh.com`.

> **Single point of failure:** ns1 and ns2 are the same machine. If it goes down
> the domain stops resolving entirely — not just the website. A second nameserver
> on separate infrastructure (a secondary/slave zone) is the fix, and needs a
> registrar change to repoint ns2's glue.

## TLS — DNS-01, not HTTP-01

Certificates come from Let's Encrypt via the **dns-01** challenge, using hooks
that write the TXT record into our own zone:

```
/usr/local/sbin/acme-dns-auth.sh      # appends _acme-challenge TXT, bumps serial, rndc reload
/usr/local/sbin/acme-dns-cleanup.sh   # truncates the include, bumps serial, reload
```

ACME records live in `/etc/bind/acme.vidhisangh.com`, `$INCLUDE`d by the zone, so
the hooks never rewrite real records.

**Why not HTTP-01:** something upstream of this host rewrites HTTP responses for
some external clients. nginx logged `200` for every Let's Encrypt probe while the
CA reported `403` — so an intermediary, not our server, produced that status.
HTTP-01 is therefore unreliable here; dns-01 avoids the HTTP path entirely.
`sudo certbot renew --dry-run` passes, and `certbot.timer` handles renewal.

## Database

Two roles, deliberately:

- `vidhisangh_admin` — owns the schema, runs migrations (`.env.admin`). Not a superuser.
- `vidhisangh_app` — what the app connects as. `NOSUPERUSER NOBYPASSRLS`, DML only,
  no DDL. **This is what makes row-level security actually apply** — a superuser
  connection silently bypasses every RLS policy.

`app.scripts.provision_db_role` expects `CREATEROLE`/superuser to *create* the role;
here the role was created as `postgres` and only the GRANTs were applied as owner.

## First-run steps that are easy to miss

1. `python -m app.scripts.seed` — seeds the RBAC catalog (88 permissions, 20 system
   roles). **Without it registration returns 500**: `get_system_role` returns `None`,
   the user's role collection is never populated, and reading `permission_codes`
   then triggers a lazy load outside the async greenlet (`MissingGreenlet`).
2. Redis must be running — the auth rate limiter fails *open* without it, which
   removes brute-force protection rather than breaking the app loudly.
3. `TrustedHostMiddleware` in production needs the apex listed explicitly;
   `*.vidhisangh.com` does **not** match bare `vidhisangh.com` in Starlette.
   (This is also why `curl http://127.0.0.1:8000/api/v1/health` on the box
   answers 400 — check health through `https://vidhisangh.com` instead.)
4. `VS_PUBLIC_APP_URL=https://vidhisangh.com` in `.env` — the base for links the
   app sends *out* (the client-facing KYC form `/kyc/{token}`). Without it links
   are built on the default `http://localhost:4200` and clients cannot open them.
   KYC/notification emails go through the channel seam (`app/core/channels.py`);
   until `VS_SMTP_*` is configured the provider is `LogProvider` (the email is
   logged, not sent) — staff use **Copy link** on the client page in the meantime.

## Backups — must run as the superuser

**`pg_dump` as `vidhisangh_admin` silently produces a broken dump.** Tenant tables
use `FORCE ROW LEVEL SECURITY`, which applies to the table *owner* too, so the
`COPY` fails per table:

```
pg_dump: error: query failed: ERROR: query would be affected by row-level
security policy for table "api_keys"
```

`PGOPTIONS="-c app.bypass_rls=on"` does not help — a non-superuser cannot set
that GUC at connection time. Dump as the superuser, and **check the exit code**,
because a partial dump still produces a plausible-looking file with a full table
of contents:

```bash
sudo -u postgres pg_dump -d vidhisangh -Fc -f /tmp/vs.dump && echo OK || echo FAILED
```

There is still no scheduled backup — see Open items.

## Deploying a change

```bash
# backend — the .env excludes are load-bearing: without them a deploy
# overwrites production secrets with your local dev config.
rsync -az --delete \
  --exclude '.venv/' --exclude '.venv-linux/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '.env' --exclude '.env.*' --exclude 'backups/' --exclude '.pytest_cache/' \
  backend/ vidhisangh:/opt/vidhisangh/backend/   # add -n first to preview
ssh vidhisangh 'cd /opt/vidhisangh/backend && set -a && . ./.env.admin && set +a && \
    PYTHONPATH=$PWD .venv/bin/python -m alembic upgrade head && \
    sudo systemctl restart vidhisangh-api'

# frontend (built locally; the server has no node toolchain yet)
# ORDER MATTERS: ship the dist only AFTER the API above has restarted on the new
# code. The SPA is served directly by nginx, so a new dist goes live the instant
# rsync finishes — if it expects a changed response shape or a new endpoint, every
# user gets "Request validation failed" / empty pages until the API catches up.
# (0036 was rolled out in the wrong order and Legal Research was blank for the
# duration of a multi-minute table rewrite as a result.)
npx ng build && rsync -az frontend/dist/ vidhisangh:/opt/vidhisangh/frontend/dist/
# NO --delete for the dist. Bundles are content-hashed and the app is a PWA
# (ngsw): a tab that is already open — or a service worker mid-update — still
# requests the *previous* build's chunks by their old hashes. Deleting them
# turns every navigation in those tabs into a 404 ("An unexpected error
# occurred" / blank page) until a hard reload. Old hashes cost disk only;
# prune ones older than a week now and then:
#   ssh vidhisangh 'find /opt/vidhisangh/frontend/dist -name "*.js" -mtime +7 -delete'
```

## Research corpus in production

**8,209 Supreme Court judgments, reporting years 2016–2026** (decided 2015-10-07 →
2026-08-12), loaded 2026-09-23 from the CC-BY-4.0 AWS Open Data mirror of the
Court's own SCR reports. DB is 16 MB; 84 GB free.

```bash
cd /opt/vidhisangh/backend && set -a && . ./.env && set +a
PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ingest_scr_judgments \
    --year-from 2016 --year-to 2026 --count 0        # re-running is a no-op
```

Earlier years are available back to **1950** — widen `--year-from` to load them.

### High Courts — 5,626,224 order records

Punjab & Haryana (1,866,684), Delhi (390,642) and Allahabad (3,368,898), 1950–2026,
from the sibling `indian-high-court-judgments` bucket (also CC-BY-4.0).

```bash
PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ingest_hc_judgments \
    --courts phhc,delhi,allahabad --year-from 1950 --year-to 2026
PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ingest_hc_judgments --list-courts  # all 25
```

Differences from the Supreme Court corpus, all deliberate:

- **No citations.** These are eCourts order records, so `citation` is NULL and rows
  are keyed by `source_ref` (`court:cnr:date`) with `ON CONFLICT DO NOTHING`. Anything
  reading judgments must treat `citation` as optional — a `citation: str` in a response
  schema turns every search into a 500.
- **Both parquet variants are loaded.** Each partition holds `metadata.parquet` *and*
  `metadata-mobile.parquet`; the mobile file is not a duplicate (44% overlap, and it
  carries ~72k records the main file lacks), so both are read and the overlap deduped.
- **No enrichment.** Millions of order PDFs is not practical. The registry's own
  `description` is kept as a searchable snippet — it is not a headnote.
- **Quality varies by court.** Punjab & Haryana populates `disposal_nature`; Delhi
  leaves it blank. Nothing is invented to fill the gap.
- **One case, many orders.** 1,351,826 CNRs carry more than one row (1,458,709
  extra rows), each a distinct order on a distinct date — never two rows on the
  same date, so `source_ref` (`court:cnr:date`) is the right key. The 5.6M rows
  are therefore ~4.2M *cases*. Search results list orders, so one case can appear
  several times with different dates; grouping results by CNR is an open UX item.
- **Ranking is capped, and broad queries are windowed.** Above 25,000 matches the
  API returns newest-first with `ranked: false` (rank-sorting 126k hits took 6.4 s;
  3k took 0.35 s), drawn from the last 2 years first (`recent_years: 2`) so the
  planner can AND the date index with the text bitmap — 12.7k rows touched instead
  of 126k. The page says so and invites a narrower query.
- **`SET LOCAL work_mem = '96MB'` on every research query.** At the default, a
  100k-row text bitmap goes *lossy* and Postgres rechecks whole pages: measured as
  434k heap fetches for a 126k-row match. This one line was the biggest win.
- **Facets: one pass, and windowed on broad queries.** The four plain dimensions
  are aggregated in a single `GROUPING SETS` scan (five separate GROUP BYs over a
  946k-row match measured 41 s), judges in a second pass via `unnest`. When the
  results are windowed the facets are too (`recent_years`), so the sidebar always
  describes the list beside it.
- **The count is capped, and that cap drives every other decision.** "Is this set
  small enough to rank?" is answered by `count(*) FROM (… LIMIT 25001)`, which
  stops scanning as soon as it passes the cap — cheap for any query. At or below
  the cap the count is exact and results are ranked; above it, `ranked: false`,
  the total is the planner estimate (`total_is_estimate`) and results are
  windowed. **Never drive the ranked/unranked choice off the planner estimate:**
  it is 6–20× low for multi-term queries even at statistics target 1000 (0037),
  because Postgres assumes terms are independent and legal terms co-occur
  ("anticipatory" ⇒ "bail" guessed 21k, real 126k). Trusting it once made the
  API *rank* a 126k set: 8.4 s. When the estimate is itself under the cap we know
  it is wrong, so the API returns the cap with `total_is_lower_bound` and the
  page says "More than 25,000".
- **Facets are bounded by `statement_timeout` (12 s) and degrade, never 504.**
  A cold aggregation over the broadest query could outlast gunicorn's 60 s
  worker timeout (the worker is SIGKILLed; the user saw a 504). Now it is
  cancelled by Postgres (SQLSTATE 57014), caught as `FacetsTimeout`, and the
  endpoint returns the total with empty buckets and `facets_partial: true`; the
  sidebar explains. `SET LOCAL` is transaction-scoped and the session commits
  per request, so the timeout cannot leak to the next request on a pooled
  connection. nginx `proxy_read_timeout` for the API is 180 s as a backstop.
- **Registry placeholders in the judge field.** Some HC registries put status
  text where a judge belongs; "Case is not allocated to court." was the *top*
  judge facet at 74,632 rows. `normalise_judges` drops them
  (`is_placeholder_judge`); 98,149 stored `judge_text` values were nulled on
  2026-09-24. Re-check after any fresh HC ingest.
- **`ORDER BY judgment_date DESC NULLS LAST` needs its own index (0038).** The
  plain btree on `judgment_date` scanned backwards yields NULLS *first*, so the
  no-query landing list fell back to a parallel seq scan of 5.6M rows + top-N
  sort: 6.4 s on every uncached load. `ix_judgments_newest_first`
  (`judgment_date DESC NULLS LAST, created_at DESC`, partial on
  `deleted_at IS NULL`) matches the ORDER BY exactly: 1.5 ms. Do not change the
  ordering expression without changing the index to match.
- **Landing facets are windowed too.** `recent_only = is_estimate` — any set
  too large to count exactly is faceted over the last 2 years, including no
  query (a full 5.6M scan blew the 12 s timeout; the ~1M-row slice takes
  1.6 s). The sidebar says "Counts cover the last 2 years".
- **HC order PDFs live at `data/pdf/year=<decision year>/court=<code>/bench=<bench>/<file>`.**
  The metadata's `pdf_link` (`court/cnrorders/<bench>/orders/<file>`, or a bare
  `orders_<year>_<n>.pdf` for Allahabad) is the registry's own path and does
  not exist in the bucket — the first load stored it and every link 404'd.
  `ingest_hc_judgments.order_pdf_url` builds the right one; the existing 5.6M
  rows were rewritten in place (34 min, `backups/fix-order-urls.sql`). Bench for
  the bare Allahabad names comes from the CNR prefix (UPHC01 Allahabad,
  UPHC02 Lucknow). Verified 16/16 reconstructed links before the mass UPDATE.
- **Bulk backfills over `judgments` must run one at a time.** `backfill_case_parties`
  (5k-row batches) and `backfill_filing_dates` (one `UPDATE … FROM` per parquet
  file) lock overlapping rows in different orders and deadlocked (40P01) within
  minutes when run together. The parties script retries a deadlocked batch, but
  the rule is sequential — `backups/parties-after-filing.sh` waits on the other
  job's process. After any full-table UPDATE run `VACUUM (ANALYZE) judgments`.
- **Full-text extraction (0040) runs as a background job, one bundle at a time.**
  `python -m app.scripts.extract_order_text --courts delhi --year-from 2024 --year-to 2024 --workers 3`
  streams `data/tar/year=…/court=…/bench=…/data.tar` (Delhi 2024: 4.5 GB, 54k
  PDFs) — nothing is written to disk; pypdf runs in `--workers` processes on a
  4-core box. It updates `judgments` rows in batches of 200, so it must not run
  beside another bulk updater (see the deadlock note above); the queued
  `backups/extract-delhi-2024.sh` waits for the parties jobs first. The
  expression in `ix_judgments_full_text_fts` and `_FULL_TEXT_VECTOR` must stay
  byte-identical (`to_tsvector('english'::regconfig, left(coalesce(full_text, ''), 300000))`)
  or the planner silently stops using the index — check with EXPLAIN for a
  `BitmapOr` over both GIN indexes after touching either. Extending the
  generated `search_vector` instead would rewrite the table under an ACCESS
  EXCLUSIVE lock; that is why full text has its own index.
- **Corpus jobs live in `infra/jobs/` (deployed to `/opt/vidhisangh/infra/jobs/`).**
  `run_full_text.sh` extracts text for the loaded courts (Delhi → P&H →
  Allahabad, newest year first; `nice`/`ionice`; stops below `MIN_FREE_GB=12`);
  `run_new_court.sh <key>` loads a court end to end (ingest → parties → filing
  dates → text). Both wait for any other bulk `judgments` updater to exit and
  are resumable (every step skips rows already done). Logs go to `backups/`.
  **Disk budget:** ~4.8 KB/order for metadata+indexes, ~3.5 KB/order for text
  (measured 2026-09-25: 5.66M orders = 26 GB database before text). Text for
  the three loaded courts ≈ +20 GB (fits the 97 GB disk); the other 22 High
  Courts (~17–18M orders, 1.4 TB of PDFs in the bucket) ≈ +150 GB — **needs a
  ~300 GB volume first.** Do not start `run_new_court.sh` on a large court
  without it; the guard will stop it but the load/index will be half done.
- **`run_target_set.sh` is the one job to (re)start** for the agreed corpus
  (SC + UP, Delhi, P&H, Uttarakhand): it chains `run_new_court.sh uttarakhand`,
  `extract_sc_text.py`, then `run_full_text.sh` for the four courts. Log:
  `backups/target-set.log`. Kill order when stopping any runner: the shell
  script first (`pkill -f run_…sh`), then the Python extractor — otherwise the
  shell starts the next year. Nothing is lost; every batch commits.
- **Supreme Court text is the SCR volume minus the headnote.** `sc_judgment_body`
  cuts at "Case Arising From" / the JURISDICTION line; if no boundary is found
  the row is marked extracted with empty text. Never relax this: the headnote,
  index and keywords are the publisher's copyright (*EBC v. D.B. Modak*), the
  judgment itself is not (s.52(1)(q)(iv)).
- **"Rate limit exceeded" on the login page after a hard refresh (2026-09-25).**
  Three things, all fixed: (1) `refresh` shared the 10/min-per-IP credential
  bucket — a whole office behind one NAT address, each tab refreshing on boot,
  exhausted it and locked the login page too; refresh now has its own scope
  (`REFRESH_RATE_LIMIT_PER_MINUTE`, 120). (2) The access token is memory-only,
  so every tab boot rotates the refresh token; two tabs booting together
  presented the same token twice and reuse detection **revoked every
  session**. The server now treats a token rotated within
  `REFRESH_REUSE_GRACE_SECONDS` (60) as a race and chains a fresh pair; the
  client serialises boots across tabs with `navigator.locks`, waits out a 429
  and never discards tokens for anything but 401/403. (3) Reuse detection's
  "revoke all" was being **rolled back** by the error response and had never
  actually worked; it now commits first — and applies only to *rotated*
  tokens. A token revoked by logout/revoke-others gets a plain 401 (a
  signed-out device presents it on its next boot; that is not theft).
- **A "504 Gateway Timeout" toast with nothing in the nginx log is the service
  worker.** `ngsw-config.json` caches `/api/v1/**` (strategy `freshness`) and
  synthesises a 504 when the network exceeds its `timeout` and nothing is
  cached. It was 5 s — shorter than the facet query under bulk-ingest load —
  so the sidebar showed "Filters unavailable" while the API was answering
  fine. It is now 55 s (under gunicorn's 60 s). Keep it above every API
  timeout. Landing-page counts/facets are also cached for an hour per worker
  (`_LANDING_TTL_SECONDS`) so they are not recomputed under load.
- **PDF text may contain NUL bytes** (`0x00`); Postgres `text` rejects them and
  asyncpg raises `CharacterNotInRepertoireError`. `extract_order_text.pdf_text`
  strips C0 controls before writing — keep that if the extractor changes.
- **New Python dependencies must be installed in the prod venv by hand** — the
  deploy is an rsync, not a `pip install`. When `pyproject.toml` gains a
  dependency (2026-09-26: `python-docx` for the document editor's Word export),
  run `cd /opt/vidhisangh/backend && .venv/bin/pip install -e .` (or the single
  package) before restarting the API, or the first request that imports it 500s.
- **Dark mode: Material's tokens do not follow `.dark` (fixed 2026-09-26).**
  The prebuilt theme (`azure-blue.css`) is light-only and has no
  `light-dark()`; `mat-sidenav-container` paints the whole content area with
  `--mat-sys-on-background` (#1a1b1f), so every un-styled heading, `strong`
  and the top-bar username were near-invisible in dark mode while
  token-styled text (`--vs-text-muted`) looked fine. Two rules now hold it:
  the shell sets `--mat-sidenav-content-text-color` to our token, and the
  `.dark` block in `styles.scss` overrides the `--mat-sys-*` colour tokens
  (surface/on-surface/outline/primary/…) so buttons, menus, dialogs and
  snackbars follow dark mode too. Diagnose with computed colour, not by
  reading stylesheets: `scratchpad/probe_dark.py` toggles dark and prints
  `getComputedStyle(h1).color` per page. Hard-coded greys in a feature
  stylesheet (News had 18) are the other cause — always use the tokens.
- **Document editor notes.** The editor's JSON (ProseMirror) is the source of
  truth; HTML and DOCX are derived from it, so a new node/mark type must be
  taught to `docx_export.py` as well or Word silently drops it. Icons inside
  the editor must carry `class="material-icons-outlined"` (the app loads only
  the Outlined icon font; a bare `<mat-icon>` prints the ligature name).
  Lists need explicit `list-style` in `.vs-prose` because Tailwind's preflight
  removes markers. Drafts autosave 1.5 s after the last change and flush with a
  keepalive `fetch` on unload.
- **Migrations on prod use `.env.admin`**, not the service user:
  `cd /opt/vidhisangh/backend && set -a && . ./.env.admin && set +a && PYTHONPATH=$PWD .venv/bin/python -m alembic upgrade head`
  (the exact line is in the deploy section above; a `sudo -u vidhisangh` guess
  fails — there is no such OS user).

### Search performance depends on the trigram indexes

`JudgmentRepository.search` ORs `ILIKE` across `case_name`, `citation`, `headnote`
and `keywords`. All four need a `gin_trgm_ops` index (migrations 0034 + 0035) or the
planner walks `ix_judgments_judgment_date` backwards and filters every row —
**26 s per query at 5.6M rows, versus ~28 ms with them**.

These indexes match `ILIKE`. An index on the bare column does **not** serve
`lower(col) LIKE …`, so changing the repository to that form silently reverts to
full scans. `pg_trgm` must be installed by a superuser first.

### Structured search (0036): full-text ranking + facets

Migration 0036 adds `case_type` / `case_number` / `case_year` / `cause_title` /
`judge_text` and a **stored generated tsvector** `search_vector` (weighted: title A,
judges/court/type B, headnote C, acts/keywords D) with a GIN index. Search uses
`websearch_to_tsquery` — quotes, `-word`, `OR` — ranked by `ts_rank_cd`, with
`ts_headline` snippets. `GET /research/judgments/facets` returns counts by court,
year, case type, judge (per judge, not per bench) and outcome for the same filters.

- **Adding the generated column rewrites the table under an exclusive lock** —
  minutes at 5.6M rows. Pause `enrich_judgments` first and take a backup.
- The new columns are empty until the backfill runs (pure SQL, batched per court):
  ```bash
  PYTHONPATH=$PWD .venv/bin/python -m app.scripts.backfill_case_fields
  ```
  API-added judgments get the same derivations at write time via
  `app/modules/research/normalise.py`; **keep it in step with the SQL** in the
  backfill script, or one judge becomes two facet values.
- Counts and facets are cached in-process for 5 minutes (keyed by the full filter
  set; the corpus is global, nothing tenant-specific is cached).
- `search_vector` is deliberately not an ORM column — SQLite cannot hold it — so
  the test suite covers an ILIKE fallback and the FTS path is verified on Postgres.

**These are reported judgments (SCR), not daily/interim orders.** The cause-list
and daily-order feeds are a separate source and are not in this dataset.

`headnote`, `acts`, `sections`, `keywords` and `bench` are **empty** until the
enrichment pass runs, so research search is effectively case-name + citation
only. Enrichment downloads each judgment PDF (~1–2 GB, a few hours) and is
resumable — only rows with no headnote are processed:

```bash
PYTHONPATH=$PWD .venv/bin/python -m app.scripts.enrich_judgments --limit 0 --concurrency 8
```

## Open items

- **No backups.** Nothing dumps Postgres anywhere. This is the biggest gap.
- No second nameserver (see above).
- No node toolchain on the server, so frontend builds happen locally.
- Let's Encrypt registered without a contact email, so no expiry warnings:
  `sudo certbot update_account --email <you@example.com>` to add one.
- Firewall is open on 22, 53, 80, 443 (plus SNMP from one IP). `ufw status`.

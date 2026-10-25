# Production deployment — vidhisangh.com

Live at **https://vidhisangh.com** (and `www`). Single host, `203.193.166.109`,
Ubuntu 24.04. This file is the record of how it is wired; keep it current.

## Access

```
ssh vidhisangh          # ~/.ssh/config alias → ubuntu@203.193.166.109
                        # key: ~/.ssh/id_ed25519_vidhisangh (no passphrase)
```

Since 27 Sep 2026 SSH is **keys only, no root login** (drop-in
`/etc/ssh/sshd_config.d/00-hardening.conf`, which must sort before
`50-cloud-init.conf`; fail2ban guards the sshd jail). Lose the key = console
access via the hosting provider only, so keep a copy off the laptop.

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

Mail records in the zone (added 27 Sep 2026): `MX 10 mx1.titan.email.` and
`MX 20 mx2.titan.email.` (Titan hosts the mailboxes), SPF
`v=spf1 include:spf.titan.email ~all` (one SPF record only — a second one is a
permanent error), DKIM `titan1._domainkey` TXT (Titan's 1024-bit RSA key;
rotate when Titan issues a new selector), DMARC `p=reject; adkim=s; aspf=s`.
With strict alignment, Titan mail passes DMARC via DKIM (`d=vidhisangh.com`).
When the app gets its own SMTP sender, add it to the same SPF record and
publish its DKIM key under a second selector.

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
   (This is also why `curl http://127.0.0.1:8000/health` on the box
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

That is exactly what `infra/jobs/backup-db.sh` does — and it is the **one**
sanctioned superuser use on this host.

### Nightly backup (I-1) — RPO 24 h, RTO 2 h

| | |
|---|---|
| **RPO** (max data loss) | **24 hours** — one full `pg_dump -Fc` per night at 01:30 IST (`backup-db.timer`, 20:00 UTC). WAL archiving is not configured; if the business needs a tighter RPO, add `archive_command` + `pgBackRest`/`wal-g` (open item). |
| **RTO** (time to restore) | **2 hours** — measured budget for: provision/clean host (30 min) → `restore-db.sh` of the 28 GB dump (`-j 4`, ~45 min) → documents/secrets untar → smoke test → DNS/nginx cutover. Re-measure at every drill. |
| Retention | 30 days local (`RETENTION_DAYS`), pruned by the script; off-host copies keep their bucket lifecycle. |
| Encryption | `age` to the public keys in `/opt/vidhisangh/.secrets/backup_age_recipients` (the host cannot read its own backups; the identity lives with the operator, off-host). Fallback: `openssl aes-256-cbc -pbkdf2` with `/opt/vidhisangh/.secrets/backup_key`. |
| Verified before kept | `pg_dump` exit code **and** `pg_restore --list` must succeed and list `TABLE DATA` for `tenants/users/matters/documents`; anything else exits non-zero, deletes the partial file and fires `vidhisangh-job-failed@`. |
| What is included | database (`backups/db/vidhisangh-YYYYmmdd-HHMM.dump.age`), document store `VS_STORAGE_DIR` (`backups/files/documents-*.tar.zst.age`), `.secrets/` minus the backup key itself (`backups/files/secrets-*.tar.age`), `.sha256` beside each. |
| Success marker | `/opt/vidhisangh/backups/last-success` (UTC timestamp). Alert if older than 26 h. |

Install once:

```bash
sudo install -m 0755 infra/jobs/backup-db.sh infra/jobs/restore-db.sh /opt/vidhisangh/infra/jobs/
sudo install -m 0644 infra/jobs/backup-db.service infra/jobs/backup-db.timer \
                     infra/jobs/vidhisangh-job-failed@.service /etc/systemd/system/
# keys — generate the age identity OFF-HOST and copy only the public key here:
#   age-keygen -o backup_age_identity.txt   (keep in the password manager / HSM)
sudo install -m 0600 -o root -g root backup_age_recipients /opt/vidhisangh/.secrets/
sudo apt-get install -y age zstd            # (openssl fallback works without age)
sudo systemctl daemon-reload && sudo systemctl enable --now backup-db.timer
sudo systemctl start backup-db.service && tail -20 /opt/vidhisangh/backups/backup.log
```

**Off-host copy (required to close I-1 fully — needs a destination).** Set
`BACKUP_S3_URI=<rclone-remote>:<bucket>/vidhisangh` in
`/opt/vidhisangh/.secrets/backup.env` (0600) after `rclone config` as root; the
script copies `db/` and `files/` with `--immutable --checksum`. Until a bucket
exists the step logs "skipped" and the backup is local-only, which does not
survive loss of the host.

### Restore drill (quarterly — record date, duration, row counts)

```bash
# 1. pick the newest backup and restore it into a FRESH database (never over live)
LATEST=$(ls -t /opt/vidhisangh/backups/db/*.dump.* | head -1)
sudo AGE_IDENTITY=/root/backup_age_identity.txt infra/jobs/restore-db.sh "$LATEST" vidhisangh_drill
# 2. the script prints alembic_version + row counts + count of FORCE RLS tables;
#    compare with production:  sudo -u postgres psql -d vidhisangh -Atc "select count(*) from matters"
# 3. smoke-test: point a copy of backend/.env at VS_POSTGRES_DB=vidhisangh_drill,
#    run  PYTHONPATH=$PWD .venv/bin/python -m app.scripts.provision_db_role --check  and log in
# 4. drop it:  sudo -u postgres dropdb vidhisangh_drill
# 5. write the drill down in docs/ops/restore-drills.md: date, backup file, wall time, checks
```

Real disaster: restore into `vidhisangh_restore_<stamp>`, run steps 2–3, then
promote with `ALTER DATABASE ... RENAME` (the script prints the exact statements),
untar `documents-*.tar.zst.age` into `VS_STORAGE_DIR` and `secrets-*.tar.age`
into `/opt/vidhisangh/.secrets`, restart `vidhisangh-api`.

### Maintenance role (VACUUM without the superuser)

The corpus jobs used to run `sudo -u postgres psql ... VACUUM`. They now connect
as a dedicated `vidhisangh_maint` role through `PGPASSFILE` (A-28):

```sql
CREATE ROLE vidhisangh_maint LOGIN PASSWORD '<from .secrets>' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE vidhisangh TO vidhisangh_maint;
GRANT USAGE ON SCHEMA public TO vidhisangh_maint;
-- PostgreSQL 17: per-table MAINTAIN privilege (VACUUM, ANALYZE, REINDEX, CLUSTER, REFRESH MV, LOCK)
GRANT MAINTAIN ON judgments, case_citations TO vidhisangh_maint;
-- or, for every table:  GRANT pg_maintain TO vidhisangh_maint;
```

```bash
sudo install -m 0600 -o ubuntu /dev/stdin /opt/vidhisangh/.secrets/pgpass_maint <<< "localhost:5432:vidhisangh:vidhisangh_maint:<password>"
```

`GRANT MAINTAIN` needs PostgreSQL ≥ 17 (production is 16.15 — use the
`pg_maintain` predefined role, or upgrade). The scripts also stopped exporting
the whole `.env.admin`; only `VS_POSTGRES_*`/`VS_DATABASE_URL` reach the loaders.

## Service management

```bash
sudo systemctl status  vidhisangh-api          # API (gunicorn/uvicorn, 127.0.0.1:8000)
sudo systemctl reload vidhisangh-api           # after a backend deploy: graceful, no 502 window
sudo systemctl restart vidhisangh-api          # only after .env / credential changes (reload keeps the old environment)
sudo systemctl stop    vidhisangh-api          # stop for this boot only
sudo systemctl disable vidhisangh-api          # stop auto-starting on boot
sudo journalctl -u vidhisangh-api -f           # live logs
sudo journalctl -u vidhisangh-api --since -1h -p warning

sudo systemctl list-timers 'vidhisangh-*' 'backup-db*'   # hourly news import, nightly backup
sudo systemctl start vidhisangh-official-news.service    # run the importer now
sudo journalctl -u vidhisangh-official-news -n 50
sudo journalctl -u backup-db -n 50

sudo nginx -t && sudo systemctl reload nginx   # after editing sites-available/vidhisangh.conf
sudo systemctl status postgresql redis-server named
```

Critical API, timer and scanner units carry
`OnFailure=vidhisangh-job-failed@%n.service`. The handler appends the failed
unit's last 40 journal lines to `/opt/vidhisangh/backups/job-failures.log` and
sends a concise alert to `VS_SECURITY_ALERT_EMAIL` through Titan SMTP. The
mailbox password is the same encrypted systemd credential used by the API; it
is not present in `ops.env` or the process environment.

Every uploaded document version is scanned through clamd's Unix-socket
INSTREAM protocol before storage. Production sets
`VS_MALWARE_SCAN_REQUIRED=true`; API startup and uploads fail closed when the
scanner is unavailable. `clamav-freshclam` keeps signatures current.

## Storage — where document bytes live

`VS_STORAGE_BACKEND` selects the backend in `app/core/storage.py`; the app
**refuses to start** (`assert_storage_ready()` in the lifespan) when the choice
would lose or expose documents:

| Backend | When | Startup gate |
|---|---|---|
| `s3` | **Production target.** Any S3-compatible bucket (AWS ap-south-1, MinIO). Every object is written with server-side encryption: `aws:kms` + `VS_S3_KMS_KEY_ID` when set, else `AES256`. | bucket must answer `HeadBucket`. |
| `local` | Single host (today). `VS_STORAGE_DIR` is **required** — there is no temp-dir default any more (a temp dir is world-readable and wiped on reboot). | dir must exist and be writable by the service user; in production it also logs a warning that at-rest encryption is the disk's job (I-5). |
| `memory` | Tests only. | refused in production. |

Production `.env` today:

```
VS_STORAGE_BACKEND=local
VS_STORAGE_DIR=/opt/vidhisangh/documents        # 0700 ubuntu; on the LUKS volume once I-5 is done
VS_MAX_UPLOAD_BYTES=26214400                    # = nginx client_max_body_size 25m
```

Moving to S3: create the bucket (versioning on, public access blocked, default
SSE-KMS), set `VS_S3_*`, flip `VS_STORAGE_BACKEND=s3`, then copy the existing
tree with `aws s3 sync /opt/vidhisangh/documents s3://<bucket>/ --sse aws:kms`.
Keys are `tenant_id/document_id/<hex>` in both backends, so no DB change is
needed. Deleting a document now deletes every version's bytes immediately (A-13);
soft-deleted rows stay for the audit trail.

Uploads (A-22): 25 MiB cap enforced three times (browser pre-check, nginx 413,
app 413 while streaming); allow-list `pdf doc docx xls xlsx pptx txt csv rtf odt
png jpg jpeg gif webp zip` (`VS_ALLOWED_UPLOAD_TYPES` overrides); magic-byte
sniffing rejects a mismatch with 415 and the **sniffed** type is what is stored
and served, with RFC 6266 `filename*=` downloads.

## CI

`.github/workflows/ci.yml` runs on every push/PR: ruff + `mypy --strict app/`,
pytest with the coverage gate from `pyproject.toml` (`fail_under = 85`),
`npm ci && ng build`, `pip-audit` on the production lock, `npm audit --omit=dev
--audit-level=high`, gitleaks (full history), trivy (fs + built images), a
CycloneDX/SPDX SBOM artifact, and a no-push build of both Dockerfiles.
`codeql.yml` scans Python + TypeScript weekly and on PRs; `dependabot.yml` opens
weekly update PRs for pip, npm, GitHub Actions, Docker and compose. Turn on
branch protection for `main` requiring "CI" and "CodeQL".

Locally: `pip install pre-commit && pre-commit install` (ruff + gitleaks on commit).

### Lock file

Runtime dependencies are installed **only** from the hash-pinned locks
(`backend/requirements.lock` = runtime + storage/search/ai extras;
`requirements-dev.lock` adds test/lint tooling). The Dockerfile and CI use
`pip install --require-hashes --no-deps`, so a tampered or substituted wheel
fails the build. Regenerate after editing `pyproject.toml` dependencies:

```bash
cd backend
.venv-linux/bin/python -m pip install -U <changed package>        # upgrade the venv first
.venv-linux/bin/python -m pip freeze --exclude-editable > /tmp/constraints.txt
python3 -m venv --without-pip /tmp/lockenv
for set in "storage,search,ai" "dev,storage,search,ai"; do
  .venv-linux/bin/python -m pip --python /tmp/lockenv/bin/python install --dry-run \
     --ignore-requires-python -c /tmp/constraints.txt --report /tmp/lock-$set.json ".[$set]"
done
# then hashes: for each name==version in the reports, fetch
#   https://pypi.org/pypi/<name>/<version>/json → urls[].digests.sha256 (all files, so the
#   lock works for any platform) and write "name==ver \ --hash=sha256:…" lines.
# (The one-off script used on 2026-09-27 is in the CI notes; pip-compile --generate-hashes
#  from pip-tools produces the same shape if you prefer a tool.)
.venv-linux/bin/python -m pip_audit --require-hashes --disable-pip -r requirements.lock
```

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
    sudo systemctl reload vidhisangh-api'
# reload = gunicorn HUP (drop-in graceful-reload.conf, 15 Oct 2026): new workers
# start on the new code while the old ones finish, so phones never see a 502
# mid-deploy. Use restart only when .env or a systemd credential changed.

# frontend (built locally; the server has no node toolchain yet)
# ORDER MATTERS: ship the dist only AFTER the API above has restarted on the new
# code. The SPA is served directly by nginx, so a new dist goes live the instant
# rsync finishes — if it expects a changed response shape or a new endpoint, every
# user gets "Request validation failed" / empty pages until the API catches up.
# (0036 was rolled out in the wrong order and Legal Research was blank for the
# duration of a multi-minute table rewrite as a result.)
npm run build && rsync -az frontend/dist/ vidhisangh:/opt/vidhisangh/frontend/dist/
# BARE-ACT PAGES (since 13 Oct 2026): public/acts/** (~3,750 pages, gitignored)
# and public/sitemap.xml are generated from content/acts/*.json by
# `npm run build:acts`. BUILD WITH `npm run build` (it runs that first), not a
# bare `npx ng build`, or the deploy ships no act pages while the sitemap lists them. The JSON is
# extracted from the official PDFs by `python3 scripts/act_sections.py` (needs
# poppler's pdftotext; one-off). The service worker must keep `!/acts/**` in
# navigationUrls, or returning visitors get the app shell on those pages.
# PRERENDERED PUBLIC PAGES (since 13 Oct 2026): `ng build` (production) writes
# static HTML for /, /help, /privacy, /terms, /trust, /auth/login and
# /auth/register (dist/.../browser/<route>/index.html) plus index.csr.html, the
# client-side shell for every other route. nginx (both server blocks in
# /etc/nginx/sites-available/vidhisangh) must use
#   try_files $uri $uri/index.html /index.csr.html;
# never /index.html as the fallback: that is now the prerendered home page.
# The mobile build (`build:mobile`) stays client-only (`"server": false`).
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

- **Backups are local-only until `BACKUP_S3_URI` points at an off-host bucket** (see Backups). No WAL archiving (RPO 24 h).
- Disk is unencrypted (I-5): put `VS_STORAGE_DIR` and the Postgres data dir on a LUKS volume.
- No second nameserver (see above).
- No node toolchain on the server, so frontend builds happen locally.
- Let's Encrypt registered without a contact email, so no expiry warnings:
  `sudo certbot update_account --email <you@example.com>` to add one.
- Firewall is open on 22, 53, 80, 443 (plus SNMP from one IP). `ufw status`.

## Auth changes 2026-09-27 (security audit A-1/2/7/8/9/11/14/18/19/20/21/23/24/26/27/33/34)

Migration **0050_auth_hardening** (after 0049_privacy). Run it with `.env.admin` as
usual; it hashes every existing portal / KYC token in place (links already sent
keep working) and nulls the clear-text column.

### New / changed environment variables (`backend/.env`)

| Variable | Default | Production |
|---|---|---|
| `VS_SECRET_KEY` | **required, no default** (≥ 32 chars) | Already set. Never rotate casually: it still signs HS256 tokens in dev and derives the sub-keys below when they are unset. |
| `VS_REFRESH_TOKEN_PEPPER` | derived (= SECRET_KEY, so existing sessions survive) | Set a separate 64-char random value. **Setting it signs everyone out once.** |
| `VS_BACKUP_CODE_PEPPER` | derived (= SECRET_KEY) | Set separately. **Setting it invalidates every MFA backup code** — announce it. |
| `VS_LINK_TOKEN_PEPPER` | derived (sha256 label `link-token`) | Set separately **before** running 0050 if you want a non-derived value; changing it afterwards breaks every portal/KYC/reset link already issued. |
| `VS_BLIND_INDEX_PEPPER` | derived | Set separately (privacy agent's searchable encrypted columns). |
| `VS_FIELD_ENCRYPTION_KEYS` | derived Fernet key from SECRET_KEY (`k1`) | Comma-separated Fernet keys, **newest first**. Rotate by prepending; old rows decrypt with their `k<n>:` key id, un-prefixed legacy rows with the derived key. Generate: `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`. |
| `VS_JWT_ALGORITHM` | `HS256` | Must be `ES256`/`RS256` in production (already ES256 with `VS_JWT_PRIVATE_KEY_PATH`/`VS_JWT_PUBLIC_KEY_PATH`); HS256 is now refused unconditionally. |
| `VS_TRUSTED_PROXY_IPS` | `127.0.0.1,::1` | nginx is on loopback, so the default is right. `X-Forwarded-For` is only honoured when the TCP peer is in this list, read right-to-left. Add the LB address/CIDR if one is ever put in front. |
| `VS_RATE_LIMITING_ENABLED` | `true` | Keep `true` (production refuses `false`). Credential limiters now **fail closed (503)** when Redis is down — Redis is a hard dependency of sign-in. |
| `VS_AUTH_ACCOUNT_RATE_LIMIT_PER_MINUTE` | `10` | Per lower-cased email, on top of the per-IP bucket. |
| `VS_REGISTER_RATE_LIMIT_PER_MINUTE` | `5` | Sign-ups per IP (also throttles the 409 email-exists oracle, which is kept by product decision). |
| `VS_MFA_RATE_LIMIT_PER_MINUTE` `VS_PUBLIC_TOKEN_RATE_LIMIT_PER_MINUTE` `VS_LINK_PREVIEW_RATE_LIMIT_PER_MINUTE` `VS_UPLOAD_RATE_LIMIT_PER_MINUTE` `VS_WS_HANDSHAKE_RATE_LIMIT_PER_MINUTE` | 10 / 30 / 20 / 30 / 30 | Defaults are fine. |
| `VS_LOGIN_MAX_FAILED_ATTEMPTS` / `VS_LOGIN_LOCKOUT_MINUTES` | 5 / 15 | Lockout now actually persists (the counter is committed before the 401). |
| `VS_REFRESH_TOKEN_IN_BODY` | `false` | Keep `false` for browser sessions so refresh tokens travel only in the HttpOnly cookie. Enable only for a separately reviewed non-browser client. |
| `VS_REFRESH_COOKIE_NAME` | `vs_refresh` | — |
| `VS_INVITES_RETURN_TEMP_PASSWORD` | `false` | Keep `false`: admins get an invitation link (7 days) instead of a temporary password. |
| `VS_INVITE_TOKEN_EXPIRE_DAYS` / `VS_PASSWORD_RESET_EXPIRE_MINUTES` / `VS_EMAIL_VERIFICATION_EXPIRE_HOURS` | 7 / 30 / 48 | — |
| `VS_PORTAL_ACCESS_EXPIRE_DAYS` | `90` | Existing links get 90 days from the migration. |
| `VS_OAUTH_MOCK_ENABLED` | `false` | Never `true` in production (start-up refuses). |
| `VS_OAUTH_ALLOWED_REDIRECT_ORIGINS` | `` | Extra origins for SSO `redirect_uri`; `VS_PUBLIC_APP_URL` and `VS_BACKEND_CORS_ORIGINS` are always allowed. |
| `VS_EXPOSE_API_DOCS` | `false` | `/api/v1/docs`, `/redoc`, `openapi.json` are off in production unless this is `true`. |
| `VS_METRICS_TOKEN` | unset | Set a random value; `/metrics` then requires `Authorization: Bearer <token>` (nginx still denies it publicly). Point Prometheus at it with the header. |
| `VS_DB_ROLE_CHECK` | `true` | At boot the app queries `pg_roles` for `current_user`; SUPERUSER or BYPASSRLS **refuses to start** in production. `vidhisangh_app` passes. |
| `VS_WS_TICKET_TTL_SECONDS` | `60` | — |
| `VS_SMTP_TLS` | `true` | New typed setting (with `VS_SMTP_HOST/PORT/USER/PASSWORD/FROM`, which existed). |
| `VS_WEBAUTHN_RP_ID` / `VS_WEBAUTHN_RP_NAME` / `VS_WEBAUTHN_ORIGIN` | `localhost` / `VidhiSangh` / `http://localhost:4200` | Production: `vidhisangh.com` / `VidhiSangh` / `https://vidhisangh.com`. |

`assert_production_ready()` logs a warning for every secret still derived from
`SECRET_KEY` and for a missing `VS_METRICS_TOKEN`.

### Behaviour changes operators should know

- **Refresh token is an HttpOnly cookie** (`vs_refresh`, `Path=/api/v1/auth`,
  `SameSite=Strict`, `Secure` outside `local`). `/auth/refresh` and `/auth/logout`
  read it when the JSON body carries no token and then require the header
  `X-Requested-With: VidhiSangh` (CSRF). The SPA does not store or migrate refresh
  tokens through localStorage.
- **Logout** clears the cookie, every CacheStorage cache, all `vs.*` /
  `vidhisangh-*` localStorage keys, and broadcasts to other tabs. It returns 400
  (`nothing_revoked`) when no session matched.
- **Immediate revocation:** role change, deactivation, password change/reset and
  "sign out everywhere" bump `users.token_epoch` and write
  `vs:revoked_user:{id}` to Redis for one access-token lifetime; older access
  tokens are refused without a DB read. **If Redis is down the check is skipped**
  (tokens live out their ≤ 15 min); the refresh token is already dead in the DB.
- **Deactivating a user also revokes the API keys they created**, and every API
  key is re-validated against its creator on each use (inactive/deleted/moved
  creator → 401; scopes ∩ creator's current permissions). Keys must now carry an
  expiry ≤ 365 days.
- **MFA:** `/auth/mfa/disable` needs the current password **and** a TOTP/backup
  code; backup codes are deleted on disable and on re-enrolment; a re-enrolment
  keeps the current authenticator working until the new one is confirmed.
- **Portal / KYC links** are stored hashed. The raw token is returned once (create
  response, email); listings show `token: null`. Portal links expire
  (`expires_at`) and record `last_accessed_at`. Staff who need a link again must
  revoke and re-issue.
- **Admin "add user"** returns `invitation_url` (7-day single-use, also emailed via
  the channel seam) and `temporary_password: null` by default. A temporary
  password, when enabled, yields a session that can only call
  `/auth/change-password` (claim `pmc`); the SPA routes it to `/auth/change-password`.
- **Password reset:** `POST /auth/forgot-password` (always 202) → email link
  `/auth/reset/{token}` → `POST /auth/reset-password`. Signs every session out.
- **Email verification:** new email registrations must open `/auth/verify-email/{token}`
  before any session is issued (updated 30 Sep 2026). Existing accounts retain their
  previous access. Verification links are delivered through a durable retry queue.
- **OAuth:** `redirect_uri` must be on the app origin; an `id_token` is verified
  (JWKS, aud, iss, exp, nonce) when the provider returns one, otherwise userinfo
  must say `email_verified: true`; identities are linked by `(provider, subject)`
  in `oauth_identities` and matched by email only on first link.
- **WebSocket:** clients call `POST /auth/ws-ticket` and connect with `?ticket=`
  (60 s, single use, Redis-backed; signed 60 s JWT fallback without Redis).
  Access tokens are never accepted in WebSocket URLs.
- **Audit trail:** `auth.registered`, `auth.login`, `auth.login_failed`,
  `auth.lockout`, `auth.logout`, `auth.refresh_reuse`, `auth.password_changed`,
  `auth.password_reset_requested`, `auth.password_reset`, `auth.invite_accepted`,
  `auth.mfa_enrolled/enabled/disabled`, `auth.passkey_added/removed`,
  `auth.session_revoked`, `auth.sessions_revoked_others`, `auth.email_verified`,
  `auth.sso_login`, `auth.sso_linked`, `user.invited` — actor ids only, never
  credentials or tokens. Failures and lockouts are committed with the counter.
- **Password policy:** minimum stays 8 (product decision) plus a local deny-list
  (`app/core/data/common_passwords.txt`, matched case-insensitively and after
  stripping trailing digits/symbols and simple leet) on register / change / reset.
- **Prometheus:** `vs_ratelimit_fallback_total{scope,mode}` counts rate-limit
  checks that ran without Redis (`mode=open` allowed, `mode=closed` → 503).

## Registration alerts (30 September 2026)

Migration `0062_registration_alerts` adds a global operational outbox. Apply it
before restarting the API. Production API workers drain committed signup alerts
in the background, using row locks to coordinate across workers. SMTP delivery
runs off the event loop and retries failures with backoff up to one hour. No
Celery service is needed. Delivery is at least once: a crash after SMTP acceptance
but before the database commit can produce a duplicate email.

`VS_REGISTRATION_ALERT_EMAIL` defaults to `ds@simsononline.com`; a blank value
stops queueing new alerts. Existing pending alerts retain their original recipient.
The message includes the registrant's name/email, practice type, workspace,
registration time (IST), plan, sample-data choice and account/workspace IDs.
Passwords, verification links and session tokens are never included. Delivery
uses the existing `VS_SMTP_*` configuration. Log-only delivery is treated as a
failure and remains queued. Rows reference the user with `ON DELETE CASCADE`.

Operational checks: `registration_alert_sent`, `registration_alert_retry`, and
`registration_alert_worker_retry` events; query `registration_alerts` for rows
where `sent_at IS NULL`. The queue applies to new registrations, not historical
accounts. Local development does not automatically send queued operational mail.

### Registration release verification — 30 September 2026

Applied `0062_registration_alerts`, restarted all three API workers, then shipped
the frontend with old hashed bundles retained. Production transaction-rollback
checks passed for individual signup with/without sample data and firm signup
with sample data, including token issuance, permissions and alert insertion.
These probes suppressed verification mail, used memory-only sample storage and
left no accounts or pending alerts. `/health` returned OK; direct API `/ready`
confirmed PostgreSQL and Redis OK (public `/ready` falls through to the SPA).
Rollback code/manifests: `backups/releases/pre-registration-20260930.tgz`.

## Contact verification and WhatsApp login — 30 September 2026

Migration `0063_registration_verification` makes user email optional, adds verified
phone identity and expiring WhatsApp challenges, and stores pending verification
links encrypted on the account until SMTP acceptance. The normal login gate is
applied at token issuance, including WhatsApp, SSO and refresh. New email signups
return `verification_required` without tokens/cookies. Opening the emailed link
verifies the address; the user then signs in. Mobile-only signup proves phone
ownership with a WhatsApp code and can immediately create a session. When both
contacts are supplied, both must be verified. Existing users are not locked out.

WhatsApp OTP is sent from VidhiSangh's own number, +91 73411 00692 (display
name "VidhiSangh", phone-number ID 1414403508414088, WhatsApp account
1631376525208862), with its approved authentication template `vidhisangh_otp`:
one body parameter (the code) and a Copy-code URL button
(`VS_WA_OTP_TEMPLATE_PARAMS=code`). Until 20 Oct 2026 codes went from the
Simsondesk number +91 73411 00734 with `simsondeskotp`, whose body also took app
name, validity, call and contact numbers
(`VS_WA_OTP_TEMPLATE_PARAMS=code,app,expiry,call,contact`). Codes expire after five minutes,
are hashed with the link-token key, are consumed once, and allow five guesses.
Resends invalidate prior codes; per-phone limits are one per minute/five per hour,
in addition to the auth IP limiter. Redis failures fail closed. MFA still applies
to WhatsApp login. Expired challenge records are removed after 24 hours.

Configuration: `VS_WA_PHONE_NUMBER_ID`, `VS_WA_ACCESS_TOKEN_FILE` (prefer a systemd
runtime credential), `VS_WA_API_VERSION=v25.0`, `VS_WA_OTP_TEMPLATE`,
`VS_WA_OTP_TEMPLATE_LANG`, `VS_WA_OTP_TEMPLATE_PARAMS`, `VS_WA_OTP_CALL_NUMBER`,
`VS_WA_OTP_CONTACT`.

**Hearing reminders** use the same number and token with the utility template
`hearing_reminder` (`VS_WA_REMINDER_TEMPLATE`, `VS_WA_REMINDER_TEMPLATE_LANG=en`;
body parameters: name, date, one-line hearing list; static "Open diary" button to
`/app/calendar`). Install `infra/jobs/vidhisangh-hearing-reminders.{service,timer}`
into `/etc/systemd/system/` and `systemctl enable --now vidhisangh-hearing-reminders.timer`;
the unit loads the `wa_access_token` credential itself. Check with
`python -m app.scripts.hearing_reminders --dry-run` (counts only). Until Meta
approves the template, sends fail and are recorded as `failed` in
`hearing_reminder_sends` (no retry for that day).

**Product updates on WhatsApp** (migration **0078**, 25 Oct 2026) use the same number
and token with two approved MARKETING templates, each in `en` and `hi`:
`judicial_officer_update` (judicial officers, and members who have not picked a
profession) and `product_update` (everyone else). Body parameter: first name; static
URL buttons. Members consent on Home or in Settings → Notifications (append-only ledger
`whatsapp_updates_consents`); sends are logged per number per campaign in
`whatsapp_campaign_sends` (HMAC of the number, never the number). The script sends
**only with `--send`**; without it every run is a dry run (counts only):
`python -m app.scripts.whatsapp_updates --campaign NAME`. To schedule a campaign,
install `infra/jobs/vidhisangh-whatsapp-updates@.{service,timer}` once, then per
campaign add a timer drop-in with `OnCalendar=` and a service drop-in with
`Environment="CAMPAIGN_FLAGS=--send"` (quoted), and start
`vidhisangh-whatsapp-updates@NAME.timer`. Only consenting members are sent to unless the
flags also hold `--owner-approved` (used once, on the owner's instruction). **Never start
the unit to "test" it**: on 25 Oct 2026 an unquoted `CAMPAIGN_FLAGS=--owner-approved
--dry-run` lost its `--dry-run`, and the launch campaign went to 12 members at 22:05 IST
instead of 9:00 the next morning (logged as campaign `selftest-dry-run`). Replies to the number are not received
(no webhook), so the templates use buttons, not "reply here".

**Fee sweep** (retainer periods and dated milestones fall due): install
`infra/jobs/vidhisangh-fee-sweep.{service,timer}` the same way and
`systemctl enable --now vidhisangh-fee-sweep.timer` (00:30 UTC daily, catches up
after downtime; needs no credentials). Check with
`python -m app.scripts.fee_sweep --dry-run` (counts only, rolled back).
`GET /api/v1/auth/options` exposes only whether WhatsApp is configured. The UI
keeps mobile signup/login disabled until the credentials are configured, while
email signup remains available. No secrets are returned to the browser.

New email accounts default to `VS_REGISTRATION_REQUIRE_VERIFICATION=true`.
Public resend is generic and rate-limited; old links stop working after resend.
The delivery worker logs `verification_email_sent` / `verification_email_retry`
without links, OTPs or mail bodies. SMTP messages now include Date and Message-ID;
a disconnect on QUIT after DATA acceptance does not trigger a duplicate send.
Backup before this release: `backups/releases/pre-contact-verification-20260930.tgz`.
Do not downgrade to a non-nullable email column after mobile-only accounts exist.

Release applied successfully; email/mobile production-schema probes rolled back.
Live WhatsApp now shares the existing Simsonsts.com account/template, so
`/api/v1/auth/options` returns `whatsapp_available: true`. The incident
owner alert was resent and SMTP-accepted; its verification message also succeeded
on retry. See PROJECT_STATUS.md for test evidence and incident timestamps.

### Shared WhatsApp credential configuration

`/etc/systemd/system/vidhisangh-api.service.d/whatsapp.conf` loads
`wa_access_token` from `/etc/credstore.encrypted/vidhisangh.wa_access_token` and
sets `VS_WA_ACCESS_TOKEN_FILE=%d/wa_access_token` with the existing phone-number ID
and template settings. Simsonsts.com was only read; no account/phone migration,
webhook subscription, template change or source credential rotation was performed.
The credential was validated with a read-only Meta request. Both sites remain up.
If the shared source token is intentionally rotated later, update this encrypted
copy too; do not rotate or migrate the shared account as part of a VidhiSangh deploy.

## Push notifications (Firebase)

Firebase project `vidhisangh-2c038`, service account
`firebase-adminsdk-fbsvc@vidhisangh-2c038.iam.gserviceaccount.com`. Its key is
an encrypted systemd credential, `/etc/credstore.encrypted/vidhisangh.fcm_key`
(`systemd-creds encrypt --name=fcm_key key.json …`), loaded by the drop-in
`/etc/systemd/system/vidhisangh-api.service.d/push.conf`:

    LoadCredentialEncrypted=fcm_key:/etc/credstore.encrypted/vidhisangh.fcm_key
    Environment=VS_FCM_CREDENTIALS_FILE=%d/fcm_key

Changing it needs `daemon-reload` and `restart` (not reload). To rotate:
generate a new key in Firebase → Project settings → Service accounts, encrypt it
over the old file, restart, then delete the old key in Google Cloud → IAM →
Service accounts. Check: sending to a made-up token must return `unregistered`
(signed in, device unknown), not `failed`.

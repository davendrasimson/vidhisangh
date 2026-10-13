> **Active task (08/10/2026):** writing AI headnotes for Supreme Court judgments, newest first, with a standing go-ahead and no paid API. Start at [AI_HEADNOTES.md → Continuing in a new session](AI_HEADNOTES.md).

# VidhiSangh — handover note (27 September 2026)

For whoever picks this up next: a person, a fresh Claude session, or another
AI coding tool. Everything you need is in this repository; nothing lives only in
a chat history or a machine-local memory. Read this file first, then the three
files it points to.

## 1. Where things stand

- **Product**: multi-tenant legal-practice SaaS for Indian advocates (matters,
  clients/KYC, documents editor, billing, calendar, CRM, research library,
  network, marketplace, client portal, notifications, admin). Phases 1–5 done,
  Phase 6 (platform/hardening) done for everything that does not need external
  infra. Details: [PROJECT_STATUS.md](PROJECT_STATUS.md) (what is built),
  [ROADMAP.md](ROADMAP.md) (phase status).
- **Production**: https://www.vidhisangh.com on one Ubuntu 24.04 host
  (203.193.166.109). Wiring, deploy steps and ops runbook:
  [DEPLOYMENT.md](DEPLOYMENT.md). Security posture and go-live checklist:
  [SECURITY.md](SECURITY.md).
- **Last big change**: Matters now support tenant-configured sections and fields (`0061`), including
  required/optional text, rich text, numeric, amount, list, date, boolean and contact fields.
  Sensitive values use application encryption, may be masked on screen, and require an audited reveal;
  sensitive values are excluded from report contents. Analytics reports field completion/approved aggregates
  and now includes timesheet approvals, unbilled time, signatures, matter documents and collection follow-ups.
  Billing also includes counsel timesheets, validated Excel/CSV import,
  approval and invoice creation. Registration's removable guided workspace includes a sample
  approved time entry. Matter detail supports direct document upload/list/download through the local/S3 storage abstraction.
  Sample cleanup uses an exact UUID/object-key manifest in tenant settings, so it cannot remove
  user-created records. The security/privacy remediation is backed by
  production malware scanning, SMTP failure alerts, a hardened edge, a tested
  encrypted off-host restore, a 13/13 public DAST baseline, and an ISMS/PIMS
  governance pack. Report + per-finding status:
  [SECURITY_AUDIT_2026-09.md](SECURITY_AUDIT_2026-09.md),
  [DAST_BASELINE_2026-09-27.md](DAST_BASELINE_2026-09-27.md), and
  [governance/README.md](governance/README.md).
- **Code state**: git `master`, commit after `c5531eb` on
  `git@git.simsononline.com:saas/vidhisangh.git`. Alembic head is
  `0061_matter_custom_fields` (apply during this release). Backend suite: 300+ tests
  passing. Frontend: clean `ng build`.

## 2. Getting a working environment

Repo layout and conventions are in [../CLAUDE.md](../CLAUDE.md) (written for
Claude Code but tool-agnostic: module shape, RLS, RBAC, date format, frontend
tokens). Follow it.

```
# Backend (Python 3.13 per pyproject; 3.12 works if you install deps directly)
cd backend && python -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"
PYTHONPATH=$PWD .venv/bin/python -m pytest -o addopts="" -q     # SQLite, no Postgres/Redis needed, ~6 min

# Frontend (Angular 21)
cd frontend && npm install && npx ng build

# Real app locally: copy backend/.env.example -> backend/.env, needs Postgres.
# VS_SECRET_KEY is now REQUIRED; a random 64-hex string is fine locally.
```

Gotchas already hit:
- `pytest -q` plus the `-q` in `addopts` hides the summary line; pass
  `-o addopts=""` or check the exit code.
- On Windows the venv path is `.venv/Scripts/python.exe`; on Linux use a
  separate `.venv-linux` (gitignored) because the checked-in `.venv` is
  Windows-only.
- `ng build` hangs if you pipe it to `tail` when backgrounding; redirect to a
  log file instead.

## 3. Production access and deploy (summary; full detail in DEPLOYMENT.md)

- SSH alias `vidhisangh` (ubuntu@203.193.166.109), **keys only**, no root.
- Deploy = rsync `backend/` (excluding `.env*`, venvs) → run
  `alembic upgrade head` with `.env` then `.env.admin` sourced → `sudo systemctl
  restart vidhisangh-api` → `npx ng build` → rsync `frontend/dist/` **without**
  `--delete` (a browser mid-session still needs old hashed chunks).
- Secrets: `/opt/vidhisangh/.secrets/` and `/opt/vidhisangh/backend/.env`
  (39 keys). Never paste values into a chat or a ticket; refer to key names.
  Values containing spaces must stay quoted (the deploy sources `.env` with
  `set -a`).
- Timers: `backup-db.timer` 20:00 UTC (encrypted pg_dump + documents + secrets
  to `/opt/vidhisangh/backups/`, verified full dump 2.2 GB on 27 Sep) and
  `vidhisangh-retention.timer` 02:30 UTC (data-retention purge).
- Health: `https://www.vidhisangh.com/health` (root path, not under /api/v1).
  `/api/v1/docs` and `/metrics` are intentionally 404 in production.
- Deleting a tenant by hand needs `SET LOCAL app.audit_purge='on'` in the same
  transaction; the audit log is append-only otherwise (migration 0052).
- Verification pattern used so far: register a throwaway tenant, test in
  headless Chrome, then delete that tenant via psql on the server.

## 4. Open items, in the order they matter

All are recorded with reasons in [FUTURE_DELIVERABLES.md](FUTURE_DELIVERABLES.md);
that file is the to-do list and the owner of every deferred decision. Short
version:

**Needs the owner's input or an external service (not code)**
1. Off-host backups are pulled nightly to the owner's local machine and encrypted
   with an `age` identity that does not exist on production. See
   [BACKUP_RESTORE_TEST_2026-09-27.md](BACKUP_RESTORE_TEST_2026-09-27.md). Add a
   second automated remote destination when the S3 bucket exists.
2. Titan MX, SPF, DKIM and DMARC resolve correctly. Live SMTP uses
   `smtp.titan.email:465` with implicit TLS and the mailbox password is stored as
   the host-encrypted systemd credential `vidhisangh.smtp_password`.
3. Salil Shaida (`grievance@vidhisangh.com`) is the live Grievance Officer.
   Replace the generic postal address and have counsel review
   [PRIVACY_NOTICE.md](PRIVACY_NOTICE.md) and [TERMS.md](TERMS.md).
4. Host: add an encrypted provider volume/external KMS and a second nameserver
   on a different machine (ns1 and ns2 are the same box). SNMP is disabled and
   UDP/161 is closed. The public DAST baseline passes; commission an independent
   authenticated penetration test.
5. Storage: the user is arranging a 2 TB S3 bucket for court-order PDFs and
   document storage (`VS_STORAGE_BACKEND=s3`, S3 backend already exists).
6. GitLab branch protection needs an administrator session or API token. The
   SSH key authenticates as `@root`, but the GitLab web endpoint has no TLS and
   the account has no API credential on this machine. Enable protected `master`,
   require merge requests and successful pipelines after GitLab HTTPS is fixed.
7. Governance documents and review cadence exist. The named owners must now
   record training, internal audits, risk treatment and management-review
   minutes; formal certification has not been claimed.

**Code, next release**
8. Continue the ordered feature plan in
   [FEATURE_ROADMAP_2026_Q4.md](FEATURE_ROADMAP_2026_Q4.md), starting with unified
   search and the Today/action inbox. The first matter integration release,
   including invoices from fee events, is already live.
9. Legal research: remaining case-information steps and per-court corpus
   builds (UP, Delhi, P&H, Uttarakhand, Supreme Court) are paused until the
   S3 bucket exists. Do not scrape CAPTCHA-gated eCourts pages.
10. Mobile apps (see [MOBILE.md](MOBILE.md)): compile and sign iOS on a Mac,
    publish both store listings, then passkeys/SSO/deep links and push
    notifications in the app. The Android upload keystore lives only on the dev
    laptop in `~/.vidhisangh-signing/android/`; back it up.

Completed after the audit handover: refresh tokens are cookie-only by default;
legacy WebSocket token and webhook signature paths are removed; new directory
identities are opt-in; changed legal terms trigger an in-app re-acceptance; the
public `/trust` page and dashboard banner show the evidence-based compliance
status; `INCIDENT_RESPONSE.md` supplies the breach runbook; ClamAV scans every
document version before storage and fails closed; systemd service/job failures
write a local incident record and email the operations mailbox; Nginx blocks
sensitive paths and unknown hosts; and the production firewall no longer allows
UDP/161.

The Documents drafting workspace also supports firm-owned Word templates
(migration 0053): upload a `.docx`, infer form fields from `{{field}}` or
`[[field]]` placeholders, manage field labels/types/required status, generate an
editable draft, and save any editor document back as a reusable template.

Document e-signing is included from migration 0059: freeze a stored version,
send an ordered workflow to internal accounts or external email recipients,
external OTP verification, drawn signature and explicit consent, rejection and
cancellation, encrypted signing evidence, source/final SHA-256 checksums, a
sealed final copy and downloadable PDF audit certificate. The authenticated
inbox is under Documents → E-signatures and the external route is `/esign/:token`.

Counsel time billing is included from migration 0060. Manual entries and imported `.xlsx`/CSV
rows use the same rate precedence (matter-team override, hourly rate card, matter hourly rate),
approval workflow and duplicate-billing guard. Approved entries for a single client create a
proforma or tax invoice from Billing → Timesheets.

## 5. Things that will surprise you

- Users see: 5 failed logins lock the account for 15 minutes; sessions are
  HttpOnly cookies (no token in localStorage); new users get an invitation
  link instead of a temporary password; marketplace, online payments, client
  portal and news obey feature flags.
- PII fields (PAN, GSTIN, DOB, mobiles, etc.) are encrypted at rest with
  `VS_FIELD_ENCRYPTION_KEYS` and searched via HMAC blind indexes. Losing that
  key or the peppers makes the data unrecoverable; copies are in
  `/opt/vidhisangh/.secrets/app_peppers.env` on the host.
- The backup script must never use `grep -q` on the TOC under `pipefail`, nor
  `tee >(pg_restore --list)`; both produced false failures or truncated dumps.
- Dates are dd/mm/yyyy everywhere; never use native `<input type="date">`.
- SCR headnotes are the publisher's copyright; only judgment bodies are stored.

## 6. How to keep this handover useful

When you finish a piece of work: update PROJECT_STATUS.md (built),
FUTURE_DELIVERABLES.md (deferred, with why), ROADMAP.md (phase ticks), bump the
"Latest is 00NN" migration line in CLAUDE.md, run the full backend suite and a
clean `ng build`, commit, push to `origin master`. Then edit section 1 and 4 of
this file so the next person starts where you stopped.

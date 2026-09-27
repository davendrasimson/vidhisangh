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
- **Last big change**: a full security & privacy audit (OWASP Top 10,
  ISO 27001/27701, DPDP Act 2023, SOC 2) with all 65 findings remediated and
  deployed the same day. Report + per-finding status:
  [SECURITY_AUDIT_2026-09.md](SECURITY_AUDIT_2026-09.md) and the PDF beside it.
- **Code state**: git `master`, commit after `c5531eb` on
  `git@git.simsononline.com:saas/vidhisangh.git`. Alembic head is
  `0052_audit_purge_guard`, applied on production. Backend suite: 305 tests
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
1. Off-host backups: set `BACKUP_S3_URI` (rclone remote) in
   `/opt/vidhisangh/.secrets/backup.env`. Until then backups exist only on the
   server.
2. SMTP with SPF/DKIM: email is logged, not sent, so password reset, invitations
   and email verification do not reach users. Update the SPF record (currently
   `v=spf1 -all`) when a sender exists.
3. Replace the grievance-officer placeholders (`VS_GRIEVANCE_OFFICER_NAME/EMAIL/
   ADDRESS` in `.env`) with the real appointee; have counsel review
   [PRIVACY_NOTICE.md](PRIVACY_NOTICE.md) and [TERMS.md](TERMS.md), then bump
   `CURRENT_TERMS_VERSION` / `CURRENT_PRIVACY_NOTICE_VERSION` so users re-accept.
4. Host: full-disk encryption, a second nameserver on a different machine
   (ns1 and ns2 are the same box), a third-party penetration test, ISMS paperwork.
5. Storage: the user is arranging a 2 TB S3 bucket for court-order PDFs and
   document storage (`VS_STORAGE_BACKEND=s3`, S3 backend already exists).

**Code, next release**
6. Invoices from fee events (the user's stated next feature after matter fee
   arrangements, migration 0045). Spec is written out in FUTURE_DELIVERABLES
   under "Invoices from fee events".
7. Legal research: remaining case-information steps and per-court corpus
   builds (UP, Delhi, P&H, Uttarakhand, Supreme Court) are paused until the
   S3 bucket exists. Do not scrape CAPTCHA-gated eCourts pages.

Completed after the audit handover: refresh tokens are cookie-only by default;
legacy WebSocket token and webhook signature paths are removed; new directory
identities are opt-in; changed legal terms trigger an in-app re-acceptance; the
public `/trust` page and dashboard banner show the evidence-based compliance
status; and `INCIDENT_RESPONSE.md` supplies the breach runbook.

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

# VidhiSangh — Future Deliverables (what's left to build/enable)

Everything deliberately **deferred** because it needs infrastructure, vendor accounts, or
credentials that weren't available while building. **The user wants each of these developed
AND tested when the infra is deployed — do not silently drop them.** Grouped by what unblocks them.

Legend: 🟢 built, needs only config/credentials to go live · 🟡 needs an external service/library · 🔴 ops/security · 🧪 testing/tooling.

---

## 🟢 Built already — just add credentials/config to go live
These ship complete and mock/flow-tested; flip them on by setting env in `backend/.env`.
- **Razorpay payments (go-live)** — `payments` module + `app/core/payments.py` (migration `0019`) are built & mock-tested. Set `VS_RAZORPAY_KEY_ID`/`_KEY_SECRET`/`_WEBHOOK_SECRET` (dashboard.razorpay.com → API Keys; start in Test Mode), point the webhook at `/api/v1/payments/webhook`, then test end-to-end (order → Checkout → verify → webhook). Provider auto-switches mock→live. Frontend nginx CSP already allows Razorpay.
- **Email (SMTP) + Slack notification channels** — the channel seam (`app/core/channels.py`, migration `0024`) is live; both fall back to a log provider (`status=sent, detail="via log"`) until configured. Set `VS_SMTP_HOST` (+`VS_SMTP_USER`/`_PASSWORD`/`_FROM`/`_TLS`) and/or `VS_SLACK_WEBHOOK`. Then verify a real email/Slack post + the delivery log.
- **OAuth/OIDC SSO** — full auth-code+PKCE flow ships (`app/core/oauth.py`, `identity/oauth_service.py`, migration `0028`). Set `VS_OAUTH_GOOGLE_CLIENT_ID`/`_CLIENT_SECRET` (and/or Microsoft/LinkedIn) and register redirect URI `<frontend-origin>/auth/callback` at the provider; it then appears on the login screen automatically. SSO signs into EXISTING accounts by verified email (invite users first).
- **Passkeys / WebAuthn** — full ceremony scaffold ships (`app/core/webauthn.py`, `identity/passkey_service.py`, migration `0030`, `/app/settings/security` + login button). To enable: `pip install webauthn`, set `VS_WEBAUTHN_RP_ID`/`_ORIGIN` to your real **HTTPS** domain, serve over HTTPS. Then test the real browser ceremony (mock verifier only covers the flow, not real crypto).

## 🟡 Need an external service or library
- **Async job queue (Celery + Redis)** — move notification channel fan-out AND outbound webhook delivery OFF the inline request path. Both currently send within the caller's transaction (guarded by try/except): `notifications/service.py::_dispatch_channels` and `webhooks/service.py::emit_event`/`_deliver`. Add retries/backoff. Several items below also want Celery.
- **SMS / WhatsApp / Push / Microsoft-Teams notification channels** — the channels enum + routing exist (recorded as `skipped`, "no provider configured"). Build each provider in `app/core/channels.py` (mirror `EmailSmtpProvider`/`SlackWebhookProvider`). SMS: Twilio/MSG91 (`VS_SMS_PROVIDER_API_KEY`). WhatsApp: WhatsApp Business (`VS_WHATSAPP_API_KEY`). Push: Web-Push/VAPID or FCM. Teams: incoming webhook/connector.
- **Object storage — S3/MinIO prod backend** — implement the `s3` backend in `app/core/storage.py` (boto3/aioboto3) + presigned URLs for large files. Then: group **cover-image upload** (Phase 2), and any avatar/document-heavy flow. (`memory`/`local` backends already exist.)
- **OCR (Tesseract or a service)** — document OCR (extract text from scanned PDFs/images) for the `documents` module.
- **Document rendering** — document **preview** (render PDF/DOCX), **version diff/comparison**, **annotations**.
- **Elasticsearch / OpenSearch** — full-text search across documents (current search is name-only ILIKE) and richer research search.
- **Redis (running) + pub/sub** — multi-instance WebSocket fan-out for real-time messaging (current `ConnectionManager` is in-process/single-worker).
- **Media / WebRTC** — messaging voice notes, calls, screen-share.
- **Vector DB (pgvector/Qdrant) + LLM providers (Phase 4 AI)** — the research foundation exists (judgments corpus, boolean search, citation graph). Build a pluggable `LLMProvider` seam (like `storage.py`) then: **semantic/vector search** + similar-case discovery (embeddings), **RAG** over judgments/acts, **AI summaries** (ratio/issues/outcome), **AI drafting** (contracts/notices/petitions/opinions), **litigation assistant** (strategy/risk/chronology/cross-exam), **meeting assistant** (transcription/minutes), and **legal-news AI digests**.
- **Semantic / "Google-like" research search over the 5.6M corpus** — the user's stated goal. What exists (0036): ranked full-text search with Google-style syntax, snippets and facets, over cleanly structured fields. What it is *not*: meaning-based. "cases where bail was denied for economic offences" only works if those words appear. The path: (1) `CREATE EXTENSION vector` (pgvector is already a Python dependency; the extension is **not installed** on production), (2) an `embedding vector(…)` column + HNSW index, (3) an embedding provider behind a seam like `storage.py` (API or a local model — 5.6M rows × ~300 tokens is roughly 1.7B tokens, so cost the provider before choosing), (4) hybrid retrieval: FTS candidates ∪ vector neighbours, re-ranked, then an LLM answer with cited judgments. Embed `cause_title + headnote/description + acts` — the fields the backfill now guarantees. Do the Supreme Court corpus (38k, enriched, high-value) first; the High Court order snippets are noisy PDF headers and will embed poorly until cleaned.
- **eCourts case data — a real provider** — the seam is built (`app/core/ecourts.py`: `ECourtsClient` protocol, `ECourtsCase` normalised shape, `set_ecourts_client`), and lookup/import/refresh endpoints + the Matters UI are wired to it. What is missing is a *source*: **there is no official public eCourts API**, the case-status pages are CAPTCHA-gated, and scraping them is brittle and a terms-of-service question — so no scraper ships. To go live, write one adapter implementing `ECourtsClient` against either (a) a licensed commercial eCourts/NJDG feed, or (b) a registered NJDG data-access arrangement, then set `VS_ECOURTS_PROVIDER`. `sample` gives deterministic fake records for UI work and is refused in production. Also worth adding once a feed exists: **cause-list sync** (daily pull of next-hearing dates across all open matters) and **CNR-based case-status alerts**.
- **External integrations (vendor OAuth apps/credentials)** — Microsoft 365, Google Workspace, Zoom/Teams meetings, DigiLocker. (SMTP/Slack channels, webhooks, and API keys are already the first live integration points.)

## 🟡 Feature follow-ups (built, but production-hardening deferred)
- **Link preview (feed unfurl)** — shipped (`app/core/link_preview.py`, migration `0031`, composer + feed UI). Deferred hardening: (1) **SSRF** — the fetcher validates the initial host against private/loopback IPs but does not pin the resolved IP through redirects, so a DNS-rebinding / redirect-to-internal is still theoretically possible; pin the IP or re-validate each hop. (2) **Image re-hosting** — preview images are stored as the remote URL and rendered directly (SPA CSP allows `img-src https:`); for privacy/reliability, download + re-host via object storage (needs the S3 backend) and strip the CDN dependency.

- **Invoices from fee events — the next step after 0045 (user's stated plan, 2026-09-27).** Matter fee-event invoicing and `Invoice.client_id` are built. **Counsel time is also built (0060):** manual and Excel-imported entries resolve hourly rates (team override → card → matter), pass through approval, and create a proforma/tax invoice with a permanent invoice link. Remaining: tax defaults pulled fully from the client master (GST treatment / reverse charge / place of supply and TDS); optional automatic drafts/payment requests; retainer recurrence and included-hearing netting; and a nightly sweep for date-triggered milestones.
- **Team follow-ups.** Deactivating a user (Settings → Users) should prompt the bulk transfer; "My matters" filter on the matters list (`GET /matters?user_id=` exists); per-role capacity/workload view; conflict check against opposing parties when adding a team member.
- **Client master — follow-ups** (shipped 2026-09-26, migration 0044). (1) ✅ Clients linked to matters (0045). **Invoices** still carry free-text client names — see the fee-events item above. (2) **KYC email/SMS delivery**: the link is emailed through the channel seam, which is `LogProvider` until SMTP (`VS_SMTP_*`) is configured on production — until then staff use *Copy link*. WhatsApp/SMS delivery of the link needs the SMS provider (see "external service" above). (3) **Document capture on the KYC form** (PAN card, GST certificate, board resolution / authorisation letter) — needs the S3 storage backend for uploads from an unauthenticated page (pre-signed PUT scoped to the request token). (4) **Client portal hand-off**: after KYC is verified, offer the matter-portal magic link from the client page. (5) Optional **PAN/GSTIN online verification** against the GST public API / NSDL when credentials exist.
- **Legal research — case information, next steps** (steps 1–3 shipped 2026-09-24: fixed order links, parties/counsel/filing date, case timeline). Remaining, in the order agreed with the user:
  4. **Full order text — built (0040) and running.** `infra/jobs/run_full_text.sh` is extracting Delhi → P&H → Allahabad, newest year first (started 2026-09-25; ~5.6M PDFs, multi-day at low priority; log `backups/full-text.log`). Text is searched via its own GIN expression index — `search_vector` was deliberately not rewritten. Still to do on top of the text: **acts/sections extraction for HC rows** (0% today; regex over "Section N of the … Act" in `full_text`), and re-running `parse_counsel` over the text for P&H/Allahabad rows the extractor's first pass missed.
  - **PDF storage in the user's S3 bucket (2 TB, being arranged, 2026-09-25).** When the bucket and credentials exist: point `app/core/storage.py` (S3 backend already there) at it, add a `copy_order_pdfs.py` job that streams each court-year tar from the open-data bucket into ours under `<court>/<year>/<file>.pdf` (never via local disk), and switch `Judgment.url` to our bucket (or keep both: `source_url` + `pdf_key`). Until then links go to the open-data bucket, which works.
  5. **The other 21 High Courts — ON HOLD (user decision 2026-09-25); runner ready.** `infra/jobs/run_new_court.sh <key>` does ingest → parties → filing dates → text for one court. The set is ~17–18M orders (1.4 TB of PDFs in the bucket): ≈ +85 GB metadata/indexes and ≈ +65 GB text against a 97 GB disk with 57 GB free. **Provision a ~300 GB volume (or move Postgres to one) first**, then run courts one at a time, largest-value first (Bombay `bombay`, Madras `madras`, Karnataka `karnataka`, Telangana `telangana` …). Expect facet windows and the count cap to matter more at 4× the rows.
  - Counsel coverage is ~90% for Delhi, partial for Allahabad ("Counsel for … :-" ~32% of recent rows) and P&H ("Present:" ~65%); the rest needs the full text (step 4). SC judgments carry no counsel by design (their `headnote` is the Court's disposal, not the cause-title page).
  - Results still list *orders*; a "group by case" toggle on the search page would use `order_count` + the case view.
  - `SearchFacets.advocates` on SQLite (tests) groups the whole " | " string; Postgres unnests per advocate.

## 🔴 Security & operations hardening
- **Security & privacy audit (27 Sep 2026) — remediated the same day.** Report: [SECURITY_AUDIT_2026-09.md](SECURITY_AUDIT_2026-09.md) (+ PDF); status of every finding is in its "Remediation status" section. Code fixes shipped as migrations 0047–0052 and deployed; host hardened (SSH keys-only, fail2ban, nginx headers+CSP, XFF, log masking, Redis auth, SPF/DMARC, journald cap, nightly encrypted backups + retention timer). **Still open, needs a decision or external infra (not code):**
  - ✅ **Off-host backup and restore test** — the 27 Sep production dump, documents and secrets were encrypted with an `age` public recipient and copied to the owner's local machine; only the local machine holds the recovery identity. The restore evidence is in `BACKUP_RESTORE_TEST_2026-09-27.md`. Add an automated second remote destination when the S3 bucket exists.
  - **Disk encryption at rest** — needs a LUKS data volume or provider-side encryption; requires downtime/migration of `/var/lib/postgresql` and `/opt/vidhisangh/documents` (I-5).
  - **Secondary authoritative DNS** on separate infrastructure + repoint ns2 glue (I-11). Both current NS names resolve to `203.193.166.109`, so there is no independent secondary. ✅ `snmpd` was disabled and UDP/161 closed on 27 Sep 2026 (I-13).
  - **KMS/HSM for the field-encryption key** — keys are now separate, rotatable (`VS_FIELD_ENCRYPTION_KEYS`, key-id prefixed) but file/env-held; `crypto._load_key()` is the KMS swap point (A-7).
  - **Grievance officer follow-up** — Salil Shaida / grievance@vidhisangh.com is published. Replace the generic postal address with the official service address and have Indian privacy counsel review `docs/PRIVACY_NOTICE.md` and `docs/TERMS.md` before relying on them.
  - ✅ **SMTP** — Titan MX, SPF (`include:spf.titan.email`), DKIM (`titan1`) and strict DMARC resolve publicly. Production authenticated to `smtp.titan.email:465` over TLS on 27 Sep 2026. The password is stored as a host-encrypted systemd credential and exposed only in the service credential directory (I-9).
  - **Branch protection / required CI checks** on the git remote (`git.simsononline.com`) — CI workflows exist in-repo but the server-side policy is the owner's to enable (A-12). **Off-host git push** of the remediation commit.
  - ✅ **Session/webhook compatibility cleanup completed (27 Sep 2026)** — refresh tokens are cookie-only by default, the SPA no longer reads a legacy local-storage token, WebSockets accept only single-use tickets, and the replayable legacy webhook signature header has been removed (A-11/A-25/A-26).
  - **Peppers** `VS_REFRESH_TOKEN_PEPPER` / `VS_BACKUP_CODE_PEPPER` deliberately left derived from `SECRET_KEY` (setting them logs every user out and voids MFA backup codes); do it in a planned maintenance window (A-7).
  - **Registration enumeration** — 201/409 kept (product decision), mitigated by 5/min per-IP + per-account limits (A-21). **Team-scoped ABAC** for externals not built; their read permissions were removed instead (A-6).
  - ✅ **DAST baseline / governance pack** — the repeatable non-destructive public scan passed 13/13 checks on 27 Sep 2026; ISMS/PIMS policy, risk and supplier registers, training/audit programme and management-review cadence are in `docs/governance/`. An independent authenticated penetration test, completed training, internal-audit evidence and signed management-review minutes remain operational work.
  - **Webhook queue** is process-local (Celery remains deferred); **Google Fonts** removed (self-hosted).
- ✅ **Non-superuser Postgres role (DONE)** — provisioning shipped: `python -m app.scripts.provision_db_role --role vidhisangh_app --password …` creates a least-privilege `NOSUPERUSER NOBYPASSRLS` role (DML-only, no DDL) so RLS is actually enforced; idempotent, `--dry-run` previews SQL. Go-live checklist in `docs/SECURITY.md`; verified by `tests/test_rls_app_role.py` (DB-enforced read + `WITH CHECK` write isolation, default-deny, no-DDL, real login verified). **Remaining ops step:** in each non-local env, set `VS_POSTGRES_USER/PASSWORD` to the app role and run migrations as an admin/owner role.
- **KMS/HSM envelope encryption + secrets-manager wiring** — `EncryptedString` (MFA secret) uses an app key today.
- ✅ **Malware scanning of uploads** — production ClamAV scans bytes before storage and fails closed; automatic signatures and service-failure alerts are active. Remaining: independent penetration testing, PITR/DR beyond the tested daily backup, and ABAC policy expansion.

## 🔐 Privacy / DPDP — deferred after the 27 Sep 2026 remediation (privacy agent)
Shipped: validation errors no longer echo input; client identity data encrypted at rest with blind-index search (0049); append-only consent ledger gating client-facing sends; minor/guardian consent; user/client/tenant export; user/client/tenant erasure with legal hold and 30-day tenant grace; rights-request register; retention purge (`app/scripts/retention_purge.py`, `infra/jobs/vidhisangh-retention.*`); public `/privacy` and `/terms`; Settings → Privacy & data; lawful basis on matter parties and leads (0051); portal rights requests; privacy settings protection; directory opt-in; and a blocking terms-version re-acceptance flow. Still to do:
- **Notification bodies still carry client names** (P-12): purge covers it (365 d); moving to ids-only needs a template layer.
- **Security alert delivery** (P-6, s.8(6)): the breach runbook is now `docs/INCIDENT_RESPONSE.md`, security events are audited, and systemd service/job failures send email through the configured SMTP relay. Central application-event aggregation/SIEM remains an operations decision.
- **S3/SSE object storage activation** (P-8/A-13): the backend exists; configure the production bucket and KMS/SSE policy so purge deletes encrypted objects rather than local files.

## 🧪 Testing & tooling
- **Browser e2e (Playwright/Cypress)** — backend has an ASGI cross-module smoke (`test_smoke_journey.py`); a real browser e2e is deferred (no browser tooling in the build env).
- **Real WebAuthn verification** — install `webauthn` (+ optionally `soft-webauthn` for tests) to cover the actual attestation/assertion crypto that the mock verifier currently stands in for.

## 📱 Mobile
- Mobile app: offline mode, document scanner, camera upload, QR scanner, biometric login — needs a mobile toolchain (not in this repo).

---
### How to resume
1. Read [PROJECT_STATUS.md](PROJECT_STATUS.md) and [../CLAUDE.md](../CLAUDE.md).
2. Confirm baseline: `cd backend && .venv/Scripts/python.exe -m pytest -q` (expect 112 passing) and `cd frontend && npx ng build` (clean).
3. Pick the next item. Prefer 🟢 (fast wins once infra/creds exist) or the **non-superuser Postgres role** (🔴, security-critical). Build behind the existing seams, write tests, keep these docs updated.

## Resolved — 30 September 2026

Intermittent login “Method Not Allowed” caused by the www 301 redirect is fixed
and deployed. API calls stay on their original origin; redirects preserve methods.
See PROJECT_STATUS.md for verification.

Individual/firm registration and durable signup alerts are deployed with migration
`0062`. Signup with sample data passed production rollback checks. Live SMTP
alert delivery was not exercised by the deployment probes, which send no mail.

## WhatsApp authentication activation — resolved 30 September 2026

Email verification and registration-alert resend are deployed; the owner confirmed
receipt of the alert. Mobile/WhatsApp signup/login (migration `0063`) is enabled.
The owner authorized shared use of the existing Simsonsts.com account/template,
expressly without transferring the account or changing that live site. Its API
credential is stored separately in VidhiSangh's encrypted systemd credential store.
No source service, account, number, template, webhook or token was changed.
A real-recipient delivery test remains for the owner's first login/registration;
no test number was provided. Source token rotations must also update VidhiSangh's
encrypted copy. See DEPLOYMENT.md for the configuration.

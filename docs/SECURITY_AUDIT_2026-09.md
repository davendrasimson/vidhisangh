# VidhiSangh Security & Privacy Audit — 27 September 2026

Static review of code, configuration and the production server (vidhisangh.com) against OWASP Top 10 (2021), ISO/IEC 27001:2022 Annex A, ISO/IEC 27701, India's Digital Personal Data Protection Act 2023 (DPDP) and the SOC 2 Trust Services Criteria. No penetration test was performed. The full report with the compliance matrix lives in the shared document "VidhiSangh Security & Privacy Audit — September 2026" (Claude Docs); this file is the repo copy so the findings travel with the code.

Numbering: **A-** application/repository, **I-** infrastructure (production host), **P-** privacy. "Confirmed" = reproduced on production with a throwaway tenant (deleted afterwards).

## Executive summary

**Overall risk: High. Not ready for ISO 27001, ISO 27701, SOC 2 or a DPDP compliance claim today; foundations are unusually good and the path is clear.** 65 findings: 4 critical, 25 high, 25 medium, 11 low/info. Four confirmed on production.

Fix first:
1. **No backups** of the 28 GB production database or the document store (I-1).
2. **Brute force is unlimited**: lockout never persists (counter rolled back with the failing request) and the login limiter is bypassed with a spoofed `X-Forwarded-For` (A-1, A-2). Both confirmed.
3. **The SPA ships without security headers**: nginx `add_header` in `location` blocks drops HSTS/nosniff/Referrer-Policy from HTML and JS; no CSP or frame protection on any page (I-2, I-3).
4. **Client identity data unprotected**: PAN/GSTIN/TAN/DOB/father's name plaintext; documents on unencrypted local disk (temp-dir default, no S3 backend exists); disk unencrypted; validation errors echo passwords (P-3, A-13, I-5, A-10 — echo confirmed).
5. **DPDP obligations unbuilt**: no notice/terms (checkbox links to nothing, acceptance discarded), no export, erasure, retention, grievance contact, no security-event audit, undeclared transfers (P-1, P-4, P-6, P-11).

Also material: tree effectively not under version control with a plaintext credential file at the root; SECURITY.md claims CI, column encryption, encrypted object storage and an immutable audit log that do not exist; webhooks are a readable SSRF; any user can write the shared judgment corpus; external "client" roles list the whole firm; mock IdP is a login bypass outside production; portal links never expire; SSH allows passwords and root with no fail2ban.

Strong and to be preserved: forced RLS on all 43 tenant tables with a `NOBYPASSRLS` app role proven by tests; Argon2id, hashed rotated refresh tokens, ES256; no injection found; object-level checks in matters; RBAC escalation closed; strict API CSP; hardened systemd/Kubernetes; consent provenance and self-correcting KYC; no trackers; candid DEPLOYMENT.md.

## Infrastructure and operations (production host, inspected 27 Sep 2026)

Ubuntu 24.04.5, nginx, gunicorn (3 workers, `User=ubuntu`, hardened unit), PostgreSQL 16.15, Redis, BIND (authoritative), snmpd.

| # | Sev | Finding | Fix | Frameworks |
|---|---|---|---|---|
| I-1 | Critical | No database or file backups: no dump, WAL, off-host copy, cron or timer; `/opt/vidhisangh/backups/` holds job logs only | Nightly `pg_dump` (superuser, exit-code checked) + WAL archiving to encrypted off-host storage; 30-day retention; alert; quarterly restore drill; back up `.secrets` and documents | ISO A.8.13, A.5.30; SOC2 A1.2-3; DPDP s.8(5) |
| I-2 | High | HSTS, nosniff, Referrer-Policy declared at server level but lost on `/`, `/auth/login` and all bundles because `location /` and the asset location add their own `Cache-Control` (nginx inheritance pitfall). Only API responses carry them (from app middleware) | Repeat the `add_header` lines in every location that sets one, or use an `include`; add `preload` once verified | OWASP A05; ISO A.8.9, A.8.24; SOC2 CC6.7 |
| I-3 | High | No CSP, `X-Frame-Options`/`frame-ancestors` or `Permissions-Policy` on the SPA; `index.html` has no CSP meta | Add CSP (`default-src 'self'`, explicit Razorpay/CDN sources, `frame-ancestors 'none'`), XFO DENY, Permissions-Policy | OWASP A05; ISO A.8.26; SOC2 CC6.7 |
| I-4 | High | SSH: `PasswordAuthentication yes`, `PermitRootLogin without-password`, `X11Forwarding yes`, port 22 world-open, fail2ban inactive, `ubuntu` has `NOPASSWD: ALL` | Keys only, no root, no X11, fail2ban sshd jail, restrict 22 to known IPs/VPN, password for sudo | ISO A.8.5, A.8.2, A.8.20; SOC2 CC6.1, CC6.6 |
| I-5 | High | Data at rest unencrypted: plain ext4 on LVM, no LUKS or provider encryption | Provider volume encryption or LUKS data volume for Postgres and uploads; document key custody | ISO A.8.24; ISO 27701 6.6; DPDP s.8(5); SOC2 C1.1 |
| I-6 | Medium | `/api/v1/docs`, `/redoc`, `/openapi.json` public in production (207 routes) | Disable when `VS_ENVIRONMENT=production` or gate behind superuser | OWASP A05; ISO A.8.9 |
| I-7 | Medium | KYC and portal tokens are URL path segments and appear in nginx access logs (3 hits in the rotated log) | Mask via `map` on `$request_uri`, or move the token off the URL after first exchange; shorten expiry | OWASP A09; ISO A.8.15; SOC2 CC7.2 |
| I-8 | Medium | 8 packages upgradable incl. `apparmor`, `libaudit`; reboot-required set (kernel). unattended-upgrades active | Maintenance window; `Automatic-Reboot` at a fixed hour or livepatch | ISO A.8.8; SOC2 CC7.1 |
| I-9 | Medium | No SPF, DKIM, DMARC or MX for `vidhisangh.com`; anyone can spoof firm email (KYC links). CAA correct | `v=spf1 -all` or provider include; DMARC `p=reject`; DKIM with SMTP | ISO A.5.14, A.8.20; SOC2 CC6.7 |
| I-10 | Medium | `server: nginx/1.24.0 (Ubuntu)` (server_tokens on); CBC suites `ECDHE-ECDSA-AES128/256-SHA` accepted (no `ssl_ciphers`); TLS 1.0/1.1 refused, 1.3 works | `server_tokens off`; Mozilla intermediate ciphers; OCSP stapling | ISO A.8.24; SOC2 CC6.7 |
| I-11 | Medium | DNS single point of failure: ns1 and ns2 are this host | Secondary authoritative DNS elsewhere; repoint ns2 glue | ISO A.8.14; SOC2 A1.2 |
| I-12 | Low | Redis has no `requirepass` (loopback only, protected mode on) | Set a password from `.secrets` | ISO A.8.5 |
| I-13 | Low | SNMP v2c read-only community, reachable from one IP; cleartext community | SNMPv3 authPriv or disable | ISO A.8.20 |
| I-14 | Low | `log_connections` off, no pgaudit, no journald cap (372 MB), no retention standard | Define retention (e.g. 90 days security logs); enable connection logging; cap journald | ISO A.8.15; SOC2 CC7.2 |

Good on the host: ufw default-deny (22/53/80/443 + SNMP from one IP); Postgres/Redis loopback with `scram-sha-256`; app runs as `vidhisangh_app` (not superuser, not `BYPASSRLS`), `vidhisangh_admin` for migrations; 44 of 46 tenant tables with forced RLS (`groups`, `network_identities` cross-tenant by design); secrets 0600; ES256 with file key; systemd `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp`; HTTP→HTTPS; certbot auto-renew (ECDSA, to 22 Dec 2026); `/metrics` denied at edge; BIND authoritative-only, no transfers, version hidden; login rate-limited per IP (429 after 10); RFC 7807 errors; NTP synced.

## Findings register (application and repository)

| # | Sev | Finding | Evidence | Fix | Frameworks |
|---|---|---|---|---|---|
| A-1 | Critical | Lockout never engages: counter incremented then the request raises and the transaction rolls back. Confirmed (6 wrong then correct → 200). Unlimited password/TOTP guessing | `identity/service.py:205-209`, `core/database.py:93-95`; contrast `service.py:275-278` | Commit the counter before raising; regression test for 403 on the 6th attempt | A07; ISO A.8.5; SOC2 CC6.1 |
| A-2 | Critical | Login limiter bypassed via spoofed `X-Forwarded-For` (first element trusted; nginx appends). Confirmed (12 attempts, no 429). Fails open on Redis error; default limiter never attached | `core/ratelimit.py:27-46`, `core/deps.py:126-131` | nginx `X-Forwarded-For $remote_addr`; `--forwarded-allow-ips`; per-email bucket; fail closed on credential routes; router-wide default limiter | A07, A05; ISO A.8.5; SOC2 CC6.1/6.6 |
| A-3 | High | Webhook delivery is a readable SSRF (any URL, no private-range check, response body stored and returned) | `webhooks/schemas.py:17-19`, `core/webhook_transport.py:30-33`, `webhooks/service.py:48-60,133-143` | Reuse link-preview host guard at create/update/delivery; https only; pin IP; store status only | A10; ISO A.8.22; SOC2 CC6.6 |
| A-4 | High | Link-preview SSRF guard bypassable via redirects and DNS rebinding; no rate limit | `core/link_preview.py:50-76,130-133`; `network/router.py:65-74` | Re-validate each hop or pin the IP; per-user limit | A10 |
| A-5 | High | Any user (incl. `student`) can write the global judgments corpus and news feed; `ts_headline` output into `[innerHTML]` | `research/router.py:30-53,165`, `rbac.py:193-194`, `news/router.py:40-50`, `research/repository.py:231-236`, `research.component.html:149` | Platform-staff `research:curate`; escape before `ts_headline`; provenance flags | A01, A03, A08; ISO A.8.3; SOC2 CC6.3 |
| A-6 | High | `client`/`arbitrator`/`mediator` roles hold firm-wide `matter/document/invoice:read`; promised ABAC absent | `identity/rbac.py:187`; `matters/service.py:112`; `documents/service.py:35`; `billing/service.py:31` | Remove from external roles or enforce team membership for them | A01; ISO A.5.15, A.8.3; SOC2 CC6.3 |
| A-7 | High | `SECRET_KEY` random per-process default, not required in production; one key for HS256, refresh pepper, backup codes, Fernet; no rotation; gate accepts HS256 with a key path set | `core/config.py:69,166-180`; `core/security.py:64-69,139`; `core/crypto.py:25-30` | Require it; split keys with key-id prefix; asymmetric JWT unconditional | A02, A05; ISO A.8.24; SOC2 CC6.1 |
| A-8 | High | Mock IdP = full auth bypass in every non-production env (default env `local`) | `core/oauth.py:97-107`; `identity/oauth_service.py:148-157` | Explicit opt-in flag defaulting off | A07; ISO A.8.31 |
| A-9 | High | Portal tokens never expire, plaintext, in URL, unthrottled | `portal/models.py:21-34`; `portal/service.py:52,139-143`; `portal/router.py:183-248` | `expires_at`; peppered hash; rate limit; session exchange. Hash KYC tokens too | A07, A02; ISO A.8.5 |
| A-10 | High | Validation errors echo submitted values incl. passwords (confirmed) | `core/exceptions.py:116-129` | Strip `input`/`url` | A04; SOC2 CC6.1 |
| A-11 | High | 14-day refresh token in `localStorage`; service worker caches every `/api/v1/**` response, nothing cleared on logout | `token.service.ts:13-37`; `ngsw-config.json:28-39` | HttpOnly cookie on refresh path + CSRF; exclude authenticated routes from SW; clear caches on logout | A07, A05; SOC2 C1.1 |
| A-12 | High | One commit / one tracked file; `.gitignore` misses `.env.*`, `backups/`, certs, notes; plaintext tenant credential file at repo root; SECURITY.md claims a nonexistent CI; backend deps floor-pinned with no lock; API key hard-coded in `scripts/fetch_bare_acts.py:21` | `git ls-files`; `.gitignore:24-27`; `docs/SECURITY.md:108-111`; `backend/pyproject.toml:9-68` | Fix ignore, delete+rotate credential, private remote + branch protection, CI (lint/tests/SAST/SCA/secrets/image/SBOM), hash-pinned lock, key to env | ISO A.8.4, A.8.8, A.8.25, A.8.28, A.8.32; SOC2 CC8.1 |
| A-13 | High | Documents unencrypted on local disk; no S3 backend exists; temp-dir default; deleted bytes never removed | `core/storage.py:78-91`; `documents/service.py:241` | S3 + SSE-KMS; refuse local in production; deletion sweep; back up | A02, A05; ISO A.8.10; SOC2 C1.2 |
| A-14 | High | No startup assertion that the DB role is not superuser/`BYPASSRLS`; profile and user repos rely on RLS alone (production role is correct today) | `core/config.py:166-179`; `profile/repository.py:23-86`; `identity/repository.py:29-35` | Check `pg_roles` at boot; add tenant predicates | A01; SOC2 CC6.1 |
| A-15 | High | IaC drift: committed nginx serves plaintext with TLS/HSTS commented out and an API vhost exposing `/metrics`; production configured by hand | `infra/nginx/vidhisangh.conf:47-68,128-160` | Commit the real config (with I-2 fix); TLS mandatory in template | ISO A.8.9, A.8.32; SOC2 CC8.1 |
| A-16 | Medium | 61/270 routes without `require_permission` (network, groups, messaging, calendar, news, notifications) → `post:*`/`connection:*` decorative, `guest` can post/create groups; `:manage` does not imply `:read` so `partner`/`corporate_counsel` get 403 on lists | `network/router.py`, `groups/router.py`; `identity/schemas.py:192`; `rbac.py:107-108,180-182` | Add guards or delete codes; `:manage` ⊇ `:read`; role reachability test | A01; ISO A.5.15, A.5.18 |
| A-17 | Medium | Connections-only posts readable by id/author/comments cross-tenant; share launders to public; private group metadata readable | `network/service.py:173-209,312-314`; `network/repository.py:162,187-195`; `groups/service.py:154-157` | Visibility predicate; reduced projection | A01 |
| A-18 | Medium | MFA disable with access token only; `/mfa/*` unthrottled; backup codes survive disable | `identity/router.py:273-307`; `identity/service.py:339-368` | Password+TOTP to disable; rate limit; delete codes | A07 |
| A-19 | Medium | API keys outlive creator's privileges; no re-validation; optional expiry | `apikeys/service.py:31-47`; `admin_service.py:112-125` | Validate creator; intersect scopes; require expiry; revoke on deactivation | A07; ISO A.5.18 |
| A-20 | Medium | No security audit trail (logins, lockout, refresh reuse, MFA/password changes, exports) and `audit_events` is mutable (app role UPDATE/DELETE, `deleted_at` column) | `record_audit` 10 call sites, none in identity; `provision_db_role.py:51`; `0026_audit_events.py:37` | Audit all; REVOKE + trigger; alert on reuse/lockout | A09; ISO A.8.15, A.5.24-28; SOC2 CC7.2-3 |
| A-21 | Medium | OAuth: `email_verified` defaults true, link by email only, id token/nonce unverified, `redirect_uri` unvalidated; email verification never enforced; registration reveals existing emails | `core/oauth.py:169`; `identity/oauth_service.py:129,164-175`; `identity/schemas.py:120-122`; `identity/service.py:92-96,116` | Verify id token; store `(provider, subject)`; allow-list redirects; email verification; uniform responses | A07; ISO A.5.16 |
| A-22 | Medium | Uploads: no size cap/type allow-list, buffered in memory, client content-type stored and served; `Content-Disposition` parameter injection (documents and portal download) | `documents/router.py:93-104,231-236`; `portal/router.py:251-252` | Stream with cap; sniff types; RFC 6266 `filename*`; cap names | A04, A05; ISO A.8.7 |
| A-23 | Medium | Refresh reuse grace window lets a thief mint a parallel family; OAuth state / KYC expiry markers lost on rollback | `identity/service.py:268-281`; `identity/oauth_service.py:121`; `clients/service.py:299-301` | Bind grace to UA/family counter + alert; commit consumption first | A07 |
| A-24 | Medium | No password reset; admin temp password in API response with no forced change; role changes/deactivation leave access tokens valid ≤15 min; logout without token silently succeeds | `identity/router.py:255-269`; `admin_service.py:25-27`; `core/deps.py:69-83`; `identity/service.py:300-309` | Reset/invite tokens; `password_must_change`; session denylist; revoke by session id | A07; ISO A.5.16-18 |
| A-25 | Medium | Webhook signature over body only (replayable); inline delivery 10 s per endpoint | `webhooks/service.py:29-63` | `t=…,v1=…` over `timestamp.body`; queued delivery | A08 |
| A-26 | Medium | WebSocket token in query string; no `is_active`/revocation check; no handshake throttle | `messaging/ws.py:53-61` | Ticket auth; check user; rate limit | A07 |
| A-27 | Medium | Docs public with `persistAuthorization`; `/metrics` unauthenticated at app layer | `main.py:57-61,97` | Disable in production; authenticate metrics | A05 |
| A-28 | Medium | K8s: no NetworkPolicy, SA token mounted, mutable tags, no PDB; compose publishes DBs/OpenSearch (security disabled) on 0.0.0.0 with default creds; jobs use `sudo -u postgres` and export admin env | `infra/k8s/*`, `docker-compose.yml:12-65`, `infra/jobs/*.sh` | Policies, SAs, digests, PDBs; loopback binds; maintenance role; restrict sudoers | ISO A.8.20, A.8.22; SOC2 CC6.6 |
| A-29 | Medium | No DB TLS/timeouts (plaintext on pod network in manifests); search path has no statement timeout; ILIKE wildcards unescaped | `core/database.py:35-42`; `research/repository.py:142-221` | `ssl=require` off-host; `pool_recycle`; role `statement_timeout`; escape `%`/`_` | A05, A04 |
| A-30 | Medium | `cryptography` 49.0.0 (PYSEC-2026-3552 → 50.0.0); Angular 21.2.18: 3 high, 5 moderate (i18n XSS, sanitiser bypass, HttpTransferCache) | `pip-audit`, `npm audit` 27 Sep 2026 | Upgrade; SCA in CI | A06; ISO A.8.8 |
| A-31 | Low | Unbounded fields (login password → two 64 MiB Argon2 ops per attempt; `content_html`; MFA code; device label); DOCX export image decode/recursion/colspan unbounded | `identity/schemas.py:59-64`; `drafting/schemas.py:60,75`; `drafting/docx_export.py:102-257` | Caps; precomputed dummy hash; clamp spans/depth | A04 |
| A-32 | Low | Feature flags never enforced; `/tenants/current`, `/admin/subscription`, `/feature-flags` auth-only; unvalidated FKs (`matter_id`, `assigned_to`, advocate `user_id`); comment `parent_id` unchecked | `featureflags/service.py:45`; `tenancy/router.py:31`; `calendar/service.py:39-55` | `require_flag`; `tenant:read`; validate FKs like `require_client` | A01, A04 |
| A-33 | Low | `returnUrl` unvalidated (in-app only); `window.open` on unvalidated news URL; Google Fonts without SRI and contradicted by container CSP; 8 settings read from `os.environ` outside `Settings` (SMTP TLS off silently, WebAuthn origin localhost) | `login.component.ts:60-102`; `news.component.ts:107`; `index.html:12-23`; `core/channels.py:73-78`; `core/webauthn.py:29-37` | Validate; self-host fonts; typed settings + production gate | A05, A08 |
| A-34 | Low | Password minimum lowered to 8 (27 Sep 2026) while SECURITY.md claims ASVS L2 (12) | `core/config.py:79`; `docs/SECURITY.md:8,45` | Restore 12 or amend the claim; breached-password check | A07 |

## Privacy and DPDP Act 2023

Processor for each firm, fiduciary for its own users. Holds full client identity sets, privileged matter content (criminal/family/caste/health inferable), non-consenting third parties (opposing parties, prospects), and 5.6M public judgments searchable by name. No notice, export, erasure, retention; one encrypted column.

| DPDP | Status | Evidence |
|---|---|---|
| s.4/s.7 lawful basis | Partial | Users consent at sign-up; client contact consent recorded; no basis for parties, prospects, corpus |
| s.5 notice | Missing | Checkbox "I agree to the Terms of Service and Privacy Policy" links to nothing; no document exists; KYC form shows no notice |
| s.6(1),(3) consent | Missing | `accept_terms` validated then discarded; no version/timestamp; client consent per channel not purpose |
| s.6(4),(6) withdrawal | Partial | Unticking overwrites the original consent record; flags gate nothing; KYC emails send regardless |
| s.8(4),(5) safeguards/accuracy | Partial | RLS/hashing strong; PAN/GSTIN/DOB plaintext; docs plaintext; passwords echoed; tokens in URLs/logs. PAN/GSTIN checks are a real accuracy control |
| s.8(6) breach notification | Not achievable | No security-event audit, alerting or runbook |
| s.8(7) erasure | Missing | Soft delete only; no purge; no retention |
| s.8(9) contact | Missing | No DPO/grievance officer published |
| s.9 children | Not addressed | Minors foreseeable as clients; no flag; no tracking exists |
| s.11-13 rights/grievance | Missing/partial | No export; correction exists for clients; no erasure; no grievance channel |
| s.16 transfers | Undeclared | Google Fonts (IP to Google pre-login), operator-wide Slack webhook (cross-tenant), OAuth IdPs, SMTP, tenant webhooks; `Tenant.region` unused |

| # | Sev | Finding | Fix |
|---|---|---|---|
| P-1 | Critical | No rights machinery: no export, deletion (user/tenant), retention/purge, grievance contact; 18 soft-delete sites; Celery configured, no tasks | Export + erasure with legal hold; retention schedule + purge; grievance officer |
| P-2 | High | Validation errors echo values incl. passwords, PAN/GSTIN on public KYC (confirmed) | Strip `input`/`url` |
| P-3 | High | PAN/GSTIN/TAN/CIN/Udyam/DOB/father's name plaintext; KYC JSON duplicates + submitter IP; `EncryptedString` on one column | Encrypt with blind indexes; drop `prefill` after apply; hash IP |
| P-4 | High | No privacy notice/terms; acceptance not stored | Write, version, link, persist |
| P-5 | High | Firm cannot discharge fiduciary duties: no client notice, per-channel consent, withdrawal destroys evidence, flags gate nothing | Notice on KYC form; append-only consent events per purpose; flags gate sends; basis for parties/prospects |
| P-6 | High | Security events not audited → breach undetectable | Audit all; alert; runbook |
| P-7 | High | Audit table mutable; docs contradict each other | REVOKE + trigger; drop `deleted_at` |
| P-8 | High | Documents plaintext on local disk; no S3; temp default; bytes never deleted | S3 SSE-KMS; refuse local; sweep |
| P-9 | High | SW caches all API responses; logout clears nothing; refresh token in localStorage | Exclude routes; clear on logout; HttpOnly cookie |
| P-10 | Medium | Sign-up publishes users to global directory (26 entries visible to a new tenant, confirmed); `visibility` never read; no opt-out | Opt-in; enforce visibility; remove-me |
| P-11 | Medium | Transfers undeclared; operator-wide Slack; `region` decorative | Register + DPAs; per-tenant Slack; self-host fonts |
| P-12 | Medium | Client names/emails in notification bodies, permanent delivery log, and journal via `LogProvider` (production state) | Ids not emails; retention cap; configure SMTP |
| P-13 | Medium | No tenant offboarding: export, deletion, DPA record, privacy settings | Tenant export + cascade delete; typed privacy block |
| P-14 | Low | Expired `oauth_states`, `webauthn_challenges`, revoked refresh tokens (IP/UA), used backup codes never purged | Scheduled purge; null IP/UA on revoke |
| P-15 | Low | Minimisation: DOB/father's name/occupation unused; opposing-party contacts without basis; corpus re-published by name without documented basis | Purpose-gate fields; document basis |
| P-16 | Info | Children: no minor flag/guardian consent; no tracking (s.9(3) met by absence) | Minor flag; state in notice |
| P-17 | Info | SECURITY.md overstates (column encryption, encrypted storage, KMS, residency, TLS 1.3, immutable audit, "DPDP-ready", CI) | Rewrite as controls matrix tied to code |

## OWASP Top 10 summary

A01 weak · A02 weak · **A03 strong** (no injection found) · A04 weak · A05 weak · A06 moderate · A07 weak · A08 moderate · A09 weak · A10 weak. Routes: 270 total, 147 RBAC-protected, 107 auth-only, 16 intentionally public, 1 public write (news) that should not be.

## Compliance readiness

None certifiable today for the same reason: primitives exist, management system does not (backups, change control, monitoring, incident response, privacy process, policies, risk register, supplier management, awareness, internal audit). Path: 7-day fixes → 30-day change control/CI/monitoring → 90-day ISMS and privacy documents → external pen test and readiness assessment; ISO 27001 Stage 2 and SOC 2 Type II need 3-6 months of operating evidence after that.

## Remediation plan (summary; full acceptance criteria in the shared doc)

**Days 1-7**: backups + restore drill (I-1); commit lockout counter (A-1); trusted-proxy limiter + per-email bucket (A-2); strip `input` from 422 (A-10); nginx headers in every location + CSP/XFO/Permissions-Policy + `server_tokens off` + ciphers, commit real config (I-2, I-3, I-10, A-15); delete/rotate credential file, fix `.gitignore`, private remote + branch protection (A-12); SSH hardening + fail2ban + reboot (I-4, I-8); disable docs, authenticate metrics (I-6, A-27); webhook/link-preview SSRF guards (A-3, A-4); upgrade `cryptography` and Angular (A-30).

**Days 8-30**: hash/expire/throttle portal and KYC tokens, mask token paths (A-9, I-7); external-role scoping, guards on 61 routes, `:manage`⊇`:read` (A-6, A-16); corpus write permission + `ts_headline` escaping (A-5); split secrets, startup role assertion, storage/WebAuthn gates (A-7, A-14, A-33); mock IdP opt-in, MFA disable protection, OAuth hardening (A-8, A-18, A-21); security audit events + immutable table + alerts + breach runbook (A-20, P-6, P-7); CI + lock file + Dependabot (A-12); refresh cookie + SW cache exclusion (A-11, P-9); upload/input/DOCX/ILIKE bounds (A-22, A-29, A-31); API-key/session revocation (A-19, A-24).

**Days 31-90**: DPDP notice/terms with stored acceptance (P-4, P-5); export/erasure/retention/grievance (P-1, P-13, P-14, A-13); consent events per purpose (P-5, P-16); S3 + column encryption + KMS (A-13, P-3, P-8, A-7); transfer register, DPAs, per-tenant Slack, self-hosted fonts (P-11, A-33); directory opt-in and visibility (P-10, A-17); password reset/invite/email verification (A-24, A-21); disk encryption, Redis auth, SNMPv3, secondary DNS, log retention, SPF/DKIM/DMARC (I-5, I-9, I-11 to I-14); K8s/compose/jobs hardening (A-28); webhook/WebSocket/DB TLS/flags (A-25, A-26, A-29, A-32); rewrite SECURITY.md + ISMS policy set + risk register (P-17); external pen test, DAST, e2e tests, restore drill on record.

## Method, evidence and limitations

Five independent static reviews (auth/sessions; authz/tenancy; injection/input/frontend; privacy; build/config/IaC) citing file:line; read-only SSH inspection of the production host; external probes (`curl`, `openssl s_client`, `dig`); `pip-audit` and `npm audit`; production reproductions with a throwaway tenant (deleted). No penetration test or DAST; production `.env` values not read; no cluster to inspect; s3 backend, real WebAuthn verifier and LLM keys have no live code path; organisational controls assessed only by absence of documents. APP_AUDIT_AND_ROADMAP.md (27 Sep 2026) is consistent with these findings.


## Remediation status (updated 27 September 2026, same day)

All code findings were remediated and deployed to production the same day (migrations `0047_feature_integration` → `0048_access_control` → `0049_privacy` → `0050_auth_hardening` → `0051_lawful_basis`; backend suite 300+ tests green; frontend rebuilt with Angular 21.2.24). Re-verified on production after deploy: sixth wrong password → 403 and the correct password stays locked (A-1); rotating `X-Forwarded-For` no longer evades the limiter (A-2); 422 bodies carry only `loc/msg/type/ctx` (A-10/P-2); `/api/v1/docs`, `openapi.json` and `/metrics` return 404 (I-6, A-27); every page and asset carries HSTS, nosniff, frame-deny, Permissions-Policy and a CSP with zero violations in a real browser session (I-2, I-3); login sets an HttpOnly refresh cookie and the session restores after reload with nothing in `localStorage` (A-11); fonts self-hosted (A-33).

| Group | Closed | How |
| --- | --- | --- |
| I-1 backups | Closed on-host; off-host pending | Encrypted verified full dump taken; `backup-db.timer` nightly 20:00 UTC with restore script and RPO/RTO in DEPLOYMENT.md. **Set `BACKUP_S3_URI` for the off-host copy.** |
| I-2, I-3, I-6, I-7, I-10 | Closed | nginx snippet included in every location; CSP; `server_tokens off`; cipher list; token-masked access log; docs off in production |
| I-4 | Closed (sudo kept) | SSH keys-only, no root, no X11, fail2ban; `NOPASSWD` sudo for the deploy user kept deliberately for unattended deploys and timers |
| I-5 disk encryption, I-11 secondary DNS, I-13 SNMPv3 | **Open — infrastructure** | Need a volume migration / second host / monitoring change |
| I-8, I-9, I-12, I-14 | Closed | Packages upgraded and rebooted; SPF `-all` + DMARC `p=reject`; Redis `requirepass`; journald cap + Postgres connection logging |
| A-1, A-2, A-7, A-8, A-9, A-11, A-14, A-18, A-19, A-21, A-23, A-24, A-26, A-27, A-31, A-34 | Closed | Auth hardening (0050): committed lockout, trusted-proxy limiter with per-account bucket failing closed, required `SECRET_KEY` with split peppers and key-id MultiFernet, mock IdP opt-in, hashed expiring portal/KYC tokens, HttpOnly refresh cookie, DB-role boot check, MFA disable re-auth, API-key re-validation, OAuth subject binding and id-token verification, password reset/invitations/`password_must_change`, revocation denylist, WebSocket tickets, common-password deny-list. Residual: `REFRESH_TOKEN_IN_BODY=true` during the client transition; `?token=` WS auth and the legacy webhook header to be removed next release |
| A-3, A-4, A-5, A-6, A-16, A-17, A-20, A-25, A-32, P-10, P-11, P-12 | Closed | Access control (0048): SSRF guards with IP pinning on webhooks and link preview; `research:curate`/`news:curate`; external roles stripped of firm-wide reads; 61 routes guarded and `:manage ⊇ CRUD`; social visibility predicate; append-only hash-chained audit table with security events and operator alerts; timestamped webhook signatures with queued delivery; `require_flag`; FK validation; directory opt-in; per-tenant Slack; delivery-log masking and purge |
| A-10, P-1 to P-9, P-13 to P-17 | Closed | Privacy (0049): error `input` stripped; export/erasure for users, clients and tenants with legal hold; encrypted identifiers with blind indexes; privacy notice and terms with stored acceptance; append-only consent events gating sends; KYC notice; minors; log masking; retention purge timer; SECURITY.md rewritten. **Placeholders to replace:** grievance officer identity, counsel review of the notice/terms, SMTP for outbound mail |
| A-12, A-13, A-15, A-22, A-28, A-29, A-30, A-33 | Closed | Platform: `.gitignore`, `.env.example`, hash-pinned lock, CI/CodeQL/Dependabot/pre-commit, key out of the script, S3 backend + storage gate + deletion sweep, nginx template matching production, streamed uploads with sniffing and RFC 6266, hardened compose/Kubernetes/Helm/jobs, DB TLS and timeouts, ILIKE escaping, dependency upgrades (zero advisories), self-hosted fonts, no API caching in the service worker. **Branch protection on the remote is the owner's to enable** |

Open items that are decisions or external infrastructure rather than code are listed in FUTURE_DELIVERABLES.md under "Security & operations hardening".

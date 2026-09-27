# VidhiSangh — Security & Privacy Controls

**Last revised 27 September 2026**, rewritten after the [September 2026 security and privacy audit](SECURITY_AUDIT_2026-09.md). This is a **controls matrix**: every ✅ points at the code or configuration that implements it. Anything without evidence is listed under *Known gaps*, not claimed.

Legend: ✅ implemented (evidence cited) · 🟡 partial (what exists and what does not) · ⬜ not implemented.

> The earlier version of this document claimed CI pipelines, column-level encryption of PII, encrypted object storage, KMS envelope encryption, TLS 1.3 enforcement, an immutable audit log and "DPDP-ready" status that did not exist in the code (audit P-17, A-12). Those claims are removed; the table below is what the repository actually enforces.

## 1. Authentication and sessions

| Control | Status | Evidence |
|---|:--:|---|
| Argon2id password hashing (64 MiB, t=3, p=2), rehash on policy change | ✅ | `backend/app/core/security.py` — `_password_hasher`, `password_needs_rehash` |
| Password policy: length + upper/lower/digit/symbol (`VS_PASSWORD_MIN_LENGTH`, default 8) | ✅ | `backend/app/modules/identity/schemas.py` — `_validate_password_strength`; `core/config.py` `PASSWORD_MIN_LENGTH` |
| Short-lived JWT access tokens bound to tenant (`tid`) and session (`rtid`) | ✅ | `core/security.py` `create_access_token`; `identity/service.py` `_issue_token_pair` |
| Opaque refresh tokens stored hashed, rotated on use, reuse detection with a short race window | ✅ | `identity/service.py` `refresh` (`REFRESH_REUSE_GRACE_SECONDS`), `identity/models.py` `RefreshToken.token_hash` |
| Account lockout after 5 failures, counter committed before the error response | ✅ | `identity/service.py` `_register_failed_login` (see docstring on transactions, audit A-1) |
| Uniform login errors + dummy hash against timing side channels | ✅ | `identity/service.py` `_resolve_login_user` |
| MFA (TOTP) with encrypted secret, pending-secret enrolment, hashed single-use backup codes | ✅ | `identity/models.py` `mfa_secret`/`mfa_pending_secret` (`EncryptedString`), `mfa_backup_codes`; `identity/service.py` `_verify_mfa` |
| Passkeys (WebAuthn) — challenge table, verifier seam | ✅ | `core/webauthn.py`, `identity/passkey_service.py`; `tests/test_passkeys.py` |
| Rate limiting on credential routes, fail-closed when Redis is unavailable; per-e-mail buckets | ✅ | `core/ratelimit.py` (`fail_closed=True` limiters, `AccountRateLimiter`); `core/config.py` `RATE_LIMITING_ENABLED` |
| Session list / revoke one / revoke others | ✅ | `identity/router.py` `list_sessions`, `revoke_session`, `revoke_other_sessions` |
| Immediate access-token revocation on role change/deactivation/password change (token epoch + denylist) | ✅ | `core/revocation.py` `mark_user_revoked`; `identity/models.py` `User.token_epoch` |
| Terms/Privacy-notice acceptance persisted with version and timestamp | ✅ | `identity/models.py` `User.terms_version`, `terms_accepted_at`; `identity/service.py` `register`; `tests/test_privacy.py::test_registration_records_terms_and_user_can_export_and_erase` |
| OAuth/OIDC sign-in (Google, Microsoft, LinkedIn) with PKCE state table | 🟡 | `core/oauth.py`, `identity/oauth_service.py`, `oauth_states` table. Mock IdP is opt-in only outside production (see auth agent's changes); id-token/nonce verification per the audit A-21 items — check `identity/oauth_service.py` for current state |

## 2. Authorisation and tenant isolation

| Control | Status | Evidence |
|---|:--:|---|
| RBAC: permission catalogue → system roles → users; `require_permission()` route guards | ✅ | `identity/rbac.py` (`PERMISSIONS`, `SYSTEM_ROLES`, `expand_permissions`), `core/deps.py` `require_permission` |
| `X:manage` implies `X:create/read/update/delete` (materialised at seed) | ✅ | `identity/rbac.py` `expand_permissions` |
| External roles (client, arbitrator, mediator) hold no firm-wide practice permissions | ✅ | `identity/rbac.py` `EXTERNAL_ROLES` and role definitions (audit A-6) |
| PostgreSQL row-level security, `FORCE`d, on every tenant-scoped table; policy from `app.current_tenant`/`app.bypass_rls` | ✅ | every migration's `_rls()` helper, e.g. `alembic/versions/0044_clients.py`, `0049_privacy.py`; `core/database.py` `apply_rls_context`; `tests/test_rls_postgres.py`, `tests/test_rls_app_role.py` (run only against Postgres) |
| Application DB role is `NOSUPERUSER NOBYPASSRLS`, DML-only; migrations run as an admin role | ✅ | `app/scripts/provision_db_role.py`; `tests/test_rls_app_role.py` |
| Repositories also filter by `tenant_id` explicitly (defence in depth; holds on SQLite tests) | ✅ | e.g. `modules/clients/repository.py`, `modules/privacy/service.py` `RightsRequestService` |
| Object-level checks on matters, documents, portal | ✅ | `modules/matters/service.py`, `modules/documents/service.py`, `modules/portal/service.py` `resolve` |
| LIKE/ILIKE wildcard escaping on user-supplied search | ✅ | `core/db_utils.py` `escape_like`, used in `modules/clients/repository.py` |
| Startup assertion that the DB role is not superuser/BYPASSRLS | ✅ | `core/startup_checks.py` `assert_database_role_safe`, called from `main.py` before serving production traffic |

## 3. Data protection (at rest, in transit, in logs)

| Control | Status | Evidence |
|---|:--:|---|
| Field-level encryption (Fernet, key-id prefixed MultiFernet for rotation) | ✅ | `core/crypto.py` `EncryptedString`; used for `users.mfa_secret`, `users.mfa_pending_secret` |
| Client identity data encrypted at rest: PAN, GSTIN, TAN, CIN, Udyam, date of birth, father's/spouse's name, mobile, phone, contact-person mobile; KYC prefill and submissions (JSON) | ✅ | `modules/clients/models.py` (`EncryptedString`, `EncryptedDate`, `EncryptedJSON`, `ENCRYPTED_CLIENT_FIELDS`); data migration `alembic/versions/0049_privacy.py`; `tests/test_privacy.py::test_client_identity_encrypted_at_rest_with_blind_index_search` |
| Exact-match search over encrypted fields via HMAC-SHA256 blind indexes with a separate pepper | ✅ | `core/crypto.py` `blind_index`/`BlindIndex` (`VS_BLIND_INDEX_PEPPER`); `clients/models.py` `pan_bidx`/`gstin_bidx`/`email_bidx` + `before_insert/update` listener; `clients/repository.py` `list` |
| KYC/portal link tokens stored as peppered hashes, not plaintext | ✅ | `modules/clients/models.py` `ClientKycRequest.token_hash`; `clients/service.py` `hash_link_token` |
| Submitter IP addresses stored only in coarse form (`/24` + sha256 prefix) | ✅ | `modules/privacy/consent.py` `coarse_ip`; `clients/service.py` `PublicKycService.submit` |
| Session IP/user-agent removed on revocation and by the purge | ✅ | `modules/privacy/retention.py` `purge_refresh_tokens`; `privacy/service.py` `UserPrivacyService.erase`; `tenancy/service.py` `cancel` |
| Tokens masked in the request log context (`/kyc/<token>`, `/portal/<token>`) | ✅ | `middleware/context.py` `mask_token_path`; `tests/test_privacy.py::test_tokens_and_addresses_are_masked_in_logs` |
| Log channel provider logs a hash prefix of the recipient, never the address or body | ✅ | `core/channels.py` `address_ref`, `LogProvider.send` |
| Delivery-log rows carry masked e-mail addresses | ✅ | `modules/notifications/service.py` `mask_emails` |
| Validation errors return only `loc/msg/type` (+ scalar `ctx`) — never `input` or `url` | ✅ | `core/exceptions.py` `_public_validation_error`; `tests/test_privacy.py::test_validation_errors_do_not_echo_input` |
| Security headers on API responses (nosniff, XFO DENY, Referrer-Policy, Permissions-Policy, strict CSP, HSTS in production) | ✅ | `middleware/context.py` `SecurityHeadersMiddleware` |
| TLS termination, HSTS/CSP on the SPA | ✅ | `infra/nginx/vidhisangh.conf` includes `snippets/vidhisangh-{headers,tls,proxy}.conf` in every applicable location; production verification is in `DEPLOYMENT.md` |
| Encrypted object storage (S3 SSE) / disk encryption | 🟡 | `core/storage.py` provides S3 with SSE-S3/SSE-KMS and refuses unsafe production storage; the configured production volume/bucket and key custody remain hosting controls (I-5, A-13) |
| KMS-managed data keys | ⬜ | Keys derive from `VS_SECRET_KEY` / `VS_FIELD_ENCRYPTION_KEYS`; `core/crypto.py` is the swap point |
| Database TLS / statement timeouts | ✅ | `core/database.py` `_connect_args`, `_configure_connection` and `statement_timeout_ms` |

## 4. Privacy programme (DPDP Act 2023)

| Obligation | Status | Evidence |
|---|:--:|---|
| Notice (s.5): itemised privacy notice and terms, public pages, versioned | ✅ | `docs/PRIVACY_NOTICE.md`, `docs/TERMS.md`; `frontend/src/app/features/legal/`; `GET /api/v1/privacy/notice` (`modules/privacy/router.py`) |
| Notice on the KYC form; version stored with the declaration | ✅ | `clients/service.py` `notice_summary`, `PublicKycService.view/submit`; `clients/models.py` `ClientKycRequest.notice_version`; `frontend/.../kyc-form.component.html` |
| Consent per purpose as an append-only ledger; withdrawal never deletes the grant; flags derived from the latest event | ✅ | `modules/privacy/models.py` `ClientConsentEvent` (Postgres: `REVOKE UPDATE, DELETE` in `0049_privacy.py`); `privacy/consent.py`; `tests/test_privacy.py::test_consent_ledger_is_append_only_and_drives_flags` |
| Client-facing sends gated by consent; contractual messages (KYC link) sent on `contract` basis and marked | ✅ | `notifications/service.py` `send_to_client`; `clients/models.py` `ClientKycRequest.lawful_basis`; `tests/test_privacy.py::test_channel_sends_are_gated_by_consent_but_kyc_link_uses_contract_basis` |
| Children (s.9): minor flag, guardian fields, verifiable guardian consent required before KYC | ✅ | `clients/models.py` `is_minor`, `guardian_*`; `clients/service.py` `create_kyc_request`; `tests/test_privacy.py::test_minor_needs_guardian_consent_before_kyc` |
| Data minimisation: DOB/father's name/occupation collected only where required (folded UI, purpose note); KYC prefill nulled after apply | ✅ | `frontend/.../client-form.component.html` ("Additional identity details"); `clients/service.py` `apply_kyc` (`req.prefill = None`) |
| Right of access (s.11): user export, client export, tenant export (zip of per-table JSON) | ✅ | `privacy/router.py` `GET /privacy/me/export`; `clients/router.py` `GET /clients/{id}/export`; `tenancy/router.py` `POST /tenants/current/export` |
| Right to erasure (s.12): user self-erasure (password, sole-admin guard), client hard erasure with legal hold (8 years, `tenant:manage` override with audited reason), tenant cancellation + 30-day cascade | ✅ | `privacy/service.py` `UserPrivacyService.erase`; `clients/service.py` `erase`/`legal_holds`; `tenancy/service.py` `cancel`; `privacy/retention.py` `purge_cancelled_tenants`/`erase_tenant` |
| Rights-request register (access/correction/erasure/grievance) with SLA due date; portal entry point | ✅ | `privacy/models.py` `PrivacyRequest`; `privacy/service.py` `RightsRequestService`, `create_rights_request` |
| Grievance officer published (s.8(9), s.13) | ✅ | `privacy/config.py` `GRIEVANCE_OFFICER_*`; `/privacy` page and KYC form |
| Retention schedule enforced by a nightly purge (oauth states, passkey challenges, revoked sessions, used backup codes, deleted documents + bytes, deleted drafts, notifications, delivery log, cancelled tenants) | ✅ | `app/scripts/retention_purge.py` `PURGES`; `privacy/retention.py`; `infra/jobs/vidhisangh-retention.{service,timer}`; `tests/test_privacy.py::test_retention_purges_are_idempotent` |
| Transfers / sub-processors declared | ✅ | `docs/PRIVACY_NOTICE.md` §6; `privacy/service.py` `SUB_PROCESSORS` |
| Directory listing opt-in / withdrawal (s.6(4)) | ✅ | New identities default to `discoverable=false`; Settings → Privacy & data calls `PATCH /network/me/visibility`; `network/repository.py` filters the directory |
| Breach notification runbook (s.8(6)) | ✅ | `docs/INCIDENT_RESPONSE.md`; security events and decisions are retained in the audit log |
| Lawful-basis field on matter parties and leads | ✅ | migration `0051_lawful_basis`; `matters/models.py`, `crm/models.py` and their schemas/services |

## 5. Audit, logging, monitoring

| Control | Status | Evidence |
|---|:--:|---|
| Structured logs with request id, method and (masked) path | ✅ | `core/logging.py`, `middleware/context.py` |
| Tenant-scoped audit events for privileged actions incl. security events (register, login, lockout, MFA, password, erasure, exports, tenant cancellation) | ✅ | `modules/audit/service.py` `record_audit`; call sites in `identity/service.py` (`_audit`), `clients/service.py`, `privacy/service.py`, `tenancy/router.py` |
| Audit log tamper evidence (hash chain, verify endpoint) | ✅ | `modules/audit/router.py` `GET /admin/audit/verify` (`ChainStatus`) |
| Audit table append-only at the database level | ✅ | `0048_access_control.py` revokes mutation; `0052_audit_purge_guard.py` permits deletion only for the controlled tenant-retention transaction |
| Prometheus metrics, health/readiness probes | ✅ | `main.py` (`/metrics`, `/health`, `/ready`); `core/ratelimit.py` `RATELIMIT_FALLBACK` |
| Central log aggregation, alerting, anomaly detection | ⬜ | Deployment concern; nothing in the repo |

## 6. Application security

| Control | Status | Evidence |
|---|:--:|---|
| Pydantic v2 validation on every request body/query | ✅ | every `schemas.py` |
| Parameterised SQL only (SQLAlchemy Core/ORM); raw `text()` used only in migrations and tests | ✅ | `grep -rn "text(" backend/app` shows `core/database.py` (set_config) only |
| Outbound URL guard (SSRF) for webhooks, link previews, tenant Slack webhooks — DNS pinning, private-range rejection | ✅ | `core/link_preview.py` `assert_public_http_url`; used in `notifications/service.py` `_post_slack`, `tenancy/service.py` `set_notification_settings` |
| API versioning (`/api/v1`) | ✅ | `core/config.py` `API_V1_PREFIX`; `api/v1/router.py` |
| CORS allow-list required in production | ✅ | `core/config.py` `assert_production_ready` |
| Bearer-token auth (no cookies) → no CSRF surface today | ✅ | `core/deps.py` `HTTPBearer` |
| Upload size caps, content-type sniffing, RFC 6266 filenames | ✅ | `core/uploads.py`, `core/http_utils.py`, `documents/router.py`; nginx/Ingress enforce the matching 25 MiB cap |
| Dependency pinning / SCA / SAST / CI | ✅ | `.github/workflows/ci.yml` (ruff, mypy, pytest+coverage, `ng build`, pip-audit, npm audit, gitleaks, trivy, SBOM), `codeql.yml`, `dependabot.yml`, `.pre-commit-config.yaml`; `backend/requirements.lock` hash-pinned; `pip-audit` and `npm audit --omit=dev` clean on 27 Sep 2026 (A-12, A-30). Branch protection must be enabled on the remote by the repo owner |

## 7. Secrets and configuration

| Control | Status | Evidence |
|---|:--:|---|
| All configuration via `VS_*` environment variables; `.env` ignored | ✅ | `core/config.py` `Settings`; `.gitignore` |
| Production gate refuses DEBUG, HS256 without keys, placeholder DB password, empty CORS, rate limiting off | ✅ | `core/config.py` `assert_production_ready` |
| Separate pepper for blind indexes (`VS_BLIND_INDEX_PEPPER`), derived from `SECRET_KEY` when unset | ✅ | `core/crypto.py` `_blind_index_pepper` |
| Key rotation for field encryption (MultiFernet, key ids) | ✅ | `core/crypto.py` (auth agent's MultiFernet refactor) |
| Cloud secrets manager / KMS | ⬜ | Not integrated |

## 8. Backups and disaster recovery

| Control | Status | Evidence |
|---|:--:|---|
| Database and object-store backups, restore drills | 🟡 | `infra/jobs/backup-db.*` and `restore-db.sh`; nightly encrypted local backups are deployed. Off-host destination and a recorded restore drill remain open |

## Known gaps (tracked against the audit)

Items the audit raised that this repository does **not** yet close. Status is maintained in [`SECURITY_AUDIT_2026-09.md`](SECURITY_AUDIT_2026-09.md) and `FUTURE_DELIVERABLES.md`:

- **I-1 / I-5 / I-11 / I-13** off-host backups, disk encryption, independent secondary DNS and SNMPv3/disablement — production infrastructure work.
- **I-1** completed 27 Sep 2026: an age-encrypted production set was copied to the owner's local machine and restore-tested; repeat quarterly and add a second automated remote destination when available.
- **I-5 / A-13 / P-8** production volume or S3 SSE-KMS configuration and external key custody; the S3/SSE implementation and production storage gate are built.
- **I-11** independent secondary DNS remains open: both NS names currently resolve to the production IP. **I-13** completed 27 Sep 2026: `snmpd` disabled and UDP/161 closed.
- **P-1 / P-17** complete the named Grievance Officer's postal address and have Indian privacy counsel approve the published legal text.
- **Notification delivery** completed 27 Sep 2026: Titan MX/SPF/DKIM/DMARC are verified and production authenticated successfully to `smtp.titan.email:465` over TLS. The mailbox password is a host-encrypted systemd credential, not an environment-file value.
- **Security assurance** independent penetration test/DAST, malware scanning and central security alerting.
- **ISMS/PIMS operation** risk register, policy ownership, supplier review, staff training, internal audit, management review and accredited certification where desired. The controls are aligned; certification is not claimed.

## Reporting

Security issues: security@vidhisangh.com. Privacy grievances: Salil Shaida at grievance@vidhisangh.com, as published on [/privacy](https://vidhisangh.com/privacy).

# Rollout validation — 29 September 2026

Release recommendation: **hold rollout until the existing backend gates are green and staging integrations have been exercised**. Adding product help does not establish release readiness for the whole application.

## Delivered

- Page-specific help for workspace, detail, settings and public pages; query-aware topics for My timesheets and Bare Acts.
- Prominent Help and light-bulb controls, contextual tips, a searchable help home, and a replayable feature overview tour.
- [Printable user guide](help/user-guide.md), generated from the same articles as the application.
- Content/route regression tests and production-build browser tests, included in CI.
- Fixed an e-signature response failure: pending audit events now receive database IDs/timestamps before serialization, and event collections are explicitly loaded to avoid asynchronous lazy-loading errors.

## Validation scope

Local environment: Node 24.18.0, Python 3.12.3, Chrome; most backend tests use isolated SQLite, in-memory storage and the repository's mocked dependencies. Both PostgreSQL RLS tests also ran successfully against the configured database using their rolled-back test transactions. The backend project and CI require Python 3.13, so CI must also pass on that supported runtime.

Browser tests intercept API requests. They validate the production frontend's behavior, including form preservation and role-specific tour content. They do not validate a live backend or external providers. No production data was changed and no deployment was performed.

## Results

| Check | Result |
| --- | --- |
| Angular production build and strict template compilation | Passed |
| Help content and route coverage | 4 tests passed; all 62 articles covered by route/content checks |
| Production-build browser regressions | 8 tests passed |
| Backend full regression run, before signing fix | 323 tests: 307 passed, 16 failed |
| Backend coverage from that full run | 70.19%; required gate is 85% — failed |
| Focused backend rerun after signing fix | 6 passed: 4 signing cases and 2 custom-field cases |
| Lint and formatting for changed signing files | Passed |
| Repository-wide backend Ruff lint | 1,249 findings — failed |
| Repository-wide backend Ruff formatting | 171 files would be reformatted — failed |
| Repository-wide backend strict mypy | 810 errors across 123 files — failed |
| Frontend production dependency audit | No known vulnerabilities reported |
| Backend pinned production dependency audit | No known vulnerabilities reported |
| PostgreSQL RLS policy and application-role tests | Both passed in the full run |
| Patch whitespace check | Passed |

Browser coverage includes help search and deep links; tour Back/Next/Finish/replay; permission filtering; current-page changes; preserving an unfinished matter form; dialog focus trapping, Escape and focus restoration; article focus; public-token privacy; light/dark mode at 320px; and tablet/desktop widths through 1280px. Mobile screenshots were also captured and reviewed.

The full backend suite was run once to completion. After the signing fix, the affected signing paths and custom-field workflows were rerun; the entire suite and coverage measurement were not rerun. Thus 14 failures from the full run remain unresolved, rather than a claimed new full-suite total. The existing frontend `lint` script has no Angular lint target; production compilation and the new tests are not a substitute for a configured frontend linter.

### Unresolved test failures

| Area | Failing tests | Observed issue |
| --- | --- | --- |
| Authentication | `test_register_returns_token_pair`, `test_refresh_rotates_and_detects_reuse`, `test_refresh_reuse_after_grace_revokes_every_session` | Tests still expect refresh-token body delivery; the default now keeps it in an HttpOnly cookie, requiring the CSRF header. |
| Authentication hardening | `test_refresh_reuse_from_another_user_agent_is_theft`, `test_role_change_and_deactivation_revoke_access_tokens_immediately` | Refresh requests return 403 at the cookie/CSRF boundary before reaching the behavior under test. |
| Sessions | `test_list_and_revoke_session`, `test_revoke_other_sessions`, `test_repeat_login_replaces_same_browser_session`, `test_refresh_consolidates_pre_device_id_browser_sessions` | Refresh requests hit the same cookie/CSRF mismatch. |
| User activation | `test_deactivate_and_reactivate` | Expected 401, received 403 at refresh. |
| Upload scanning | `test_malware_is_rejected_before_storage` | Expected malware validation status 422, received unsupported media status 415. Check upload fixture/type validation ordering before considering scanner coverage established. |
| Platform support and timesheets | `test_ticket_and_platform_moderation`, `test_time_entry_approval_and_invoice` | Registration fixtures use reserved email domains rejected by email validation (422); these workflows were not reached. |
| Profile privacy | `test_profile_masters_and_dpdp_group_masking` | Response validation rejects a stored `professional_email` fixture using a reserved `.test` domain. |

The two initial signing failures (`test_internal_signature_freezes_and_seals_document`, `test_signature_requires_assigned_signer_and_consent`) are resolved in the focused rerun. Cancellation and rejection regressions were added as well. Production cookie/CSRF security was not weakened to accommodate older test assumptions.

## Remaining release checks

1. Resolve failing backend regressions and restore the coverage, lint, formatting and strict typing gates. Re-run CI on Python 3.13.
2. Repeat the passing PostgreSQL RLS tests against the intended staging migration and application-role configuration; the configured test database is not a substitute for deployment verification.
3. On staging, exercise registration, email verification, recovery, MFA/passkeys, role restrictions and organisation isolation with real browser sessions.
4. Exercise an end-to-end matter and client journey: custom sections/fields, KYC, document upload and download, draft export, signing with two test recipients, client portal, calendar, timesheets, invoice, receipt and payment reconciliation.
5. Verify configured eCourts/research providers, email delivery, payment gateway callbacks, document storage and WebSocket reconnects. Test denied access, expired links and provider failures as well as success paths.
6. Confirm migrations, backup restoration and deployment rollback against the intended release environment; complete the repository's remaining CI security scans.

These are outstanding checks, not reported as passed by the isolated test runs.

## Reproduction

```sh
cd frontend
npm ci
npm test
npm run docs:help
npx playwright install chromium
npm run test:e2e
npm audit --omit=dev --audit-level=high
```

For an existing Chrome binary, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` when running the browser suite.

On the supported backend Python environment:

```sh
cd backend
VS_DEBUG=false VS_LOG_LEVEL=WARNING VS_STORAGE_BACKEND=memory PYTHONPATH=. \
  python -m pytest -q -p no:logging --cov=app --cov-branch --cov-report=term-missing:skip-covered
ruff check app tests
ruff format --check app tests
mypy --strict app
pip-audit --strict --require-hashes --disable-pip -r requirements.lock
```

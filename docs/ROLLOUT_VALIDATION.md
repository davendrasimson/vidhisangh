# Rollout validation — 29 September 2026

Deployment: **live at https://vidhisangh.com**, 29 September 2026. The backend synced, Alembic upgrade completed, API restarted, and the frontend bundle was then published.

## Delivered

- Page-specific help for workspace, detail, settings and public pages; query-aware topics for My timesheets and Bare Acts.
- Prominent Help and light-bulb controls, contextual tips, a searchable help home, and a replayable feature overview tour.
- [Printable user guide](help/user-guide.md), generated from the same articles as the application.
- Content/route regression tests and production-build browser tests, included in CI.
- Fixed an e-signature response failure: pending audit events now receive database IDs/timestamps before serialization, and event collections are explicitly loaded to avoid asynchronous lazy-loading errors.

## Validation scope

Local environment: Node 24.18.0, Python 3.12.3, Chrome; most backend tests use isolated SQLite, in-memory storage and the repository's mocked dependencies. Both PostgreSQL RLS tests also ran successfully against the configured database using their rolled-back test transactions. The backend project and CI require Python 3.13, so CI must also pass on that supported runtime.

Browser tests intercept API requests. They validate the production frontend's behavior, including form preservation and role-specific tour content. They do not validate a live backend or external providers. Backend regression data was isolated to test databases and rolled back by the test fixtures. The production host is `vidhisangh` (`203.193.166.109`); its API, nginx, PostgreSQL and Redis remained active after deployment; direct liveness/readiness checks passed with database and Redis both healthy. The live HTTPS `/help` Playwright smoke test passed search and article deep-link navigation.

## Results

| Check | Result |
| --- | --- |
| Angular production build and strict template compilation | Passed |
| Help content and route coverage | 4 tests passed; all 62 articles covered by route/content checks |
| Production-build browser regressions | 8 tests passed |
| Backend full regression run after fixes | 325 tests passed; no test failures |
| Backend coverage | 71.30%; required gate is 85% — failed |
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

The full backend suite completed from the backend project root after all fixes. The coverage threshold still fails. The existing frontend `lint` script has no Angular lint target; production compilation and the new tests are not a substitute for a configured frontend linter.

### Resolved backend regressions

- Auth, session, activation and user-agent tests now explicitly exercise the supported refresh-token body mode; separate hardening tests retain coverage of the cookie-only default and CSRF check.
- Registration and profile fixtures now use valid example email domains.
- Malware scanning test uploads a valid PDF signature so its scanner mock is reached.
- Support-ticket updates append staff responses to the already-loaded response collection, so API responses include the reply.
- Signature responses flush generated event fields and load events explicitly before response validation.

The tests exercise supported application behavior without weakening production cookie, CSRF, validation or scanner controls.

## Remaining release checks

1. Raise backend statement/branch coverage from 71.30% to the configured 85% gate; fix the repository-wide Ruff findings, formatting failures and mypy errors; rerun CI on Python 3.13.
2. Repeat PostgreSQL RLS tests against the intended deployment migration and application-role configuration.
3. On staging, exercise registration, email verification, recovery, MFA/passkeys, role restrictions and organisation isolation with real browser sessions.
4. Exercise an end-to-end matter and client journey: custom sections/fields, KYC, document upload and download, draft export, signing with two test recipients, client portal, calendar, timesheets, invoice, receipt and payment reconciliation.
5. Verify configured eCourts/research providers, email delivery, payment gateway callbacks, document storage and WebSocket reconnects. Test denied access, expired links and provider failures as well as success paths.
6. Confirm migrations, backup restoration and deployment rollback against the intended release environment; complete the repository's remaining CI security scans.

The requested deployment proceeded after the complete backend test run passed, even though repository-wide coverage, lint, formatting and type gates remain below policy. Track those quality gates as post-deployment work; coverage remains 71.30% against the 85% requirement.

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

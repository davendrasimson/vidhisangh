# VidhiSangh application audit and delivery roadmap

**Audit date:** 27 September 2026  
**Scope:** frontend, backend, database migrations, production health, product workflows, security posture, testing, operations, data corpus, and repository hygiene.  
**Planning horizon:** immediate stabilisation, 30 days, 90 days, and 6–12 months.

For the product-feature and module-synchronization plan, see [FEATURE_INTEGRATION_ROADMAP.md](FEATURE_INTEGRATION_ROADMAP.md). That roadmap intentionally excludes the security and infrastructure work covered here.

This document is the current execution plan. The older phase descriptions in `ROADMAP.md`, `PROJECT_STATUS.md`, and `SECURITY.md` contain useful implementation history, but several counts and completion claims are stale. Update those files from this document after the first stabilisation sprint.

## Executive assessment

VidhiSangh is a broad working product rather than a prototype. It has authenticated practice management, matters, clients, documents and drafting, billing, CRM, calendars, a client portal, professional networking, legal news, a large judgment corpus, Bare Acts, research tools, administration, and a PWA shell. The production health endpoint was healthy during this audit.

The next priority should be reliability and trust. The product has outgrown its release and operations controls. The largest risks are the absence of verified backups and restore drills, almost the entire application being outside Git history, current Angular security advisories, no frontend tests, no CI configuration in the repository, incomplete route-level permission enforcement, and user research data stored only in the browser.

The recommended order is:

1. Protect the code, credentials, database, and production release process.
2. Make access control, tests, monitoring, and stored user work dependable.
3. Connect the existing practice-management features into complete daily workflows.
4. Improve legal-data provenance, versioning, citations, and search quality.
5. Add AI only after the source, citation, evaluation, and audit foundations are measurable.

## Evidence collected

- Production `GET /health` returned `status: ok`, version `0.1.0`, environment `production`.
- The latest database migration in the repository is `0046_document_client.py`.
- The Angular application exposes 40+ authenticated route destinations across 20 feature areas.
- The backend exposes substantial APIs across identity, tenancy, matters, clients, documents, drafting, billing, research, knowledge, news, portal, messaging, and administration.
- Pytest collected **171 first-party backend tests in 42 files**. The full run did not complete or emit progress within 150 seconds and was stopped, so this audit does not call the suite green.
- There are **no first-party frontend unit or end-to-end test files**.
- The most recent production frontend build is available and the PWA service worker is configured. The built directory is about 47 MB, mostly legal assets; the largest JavaScript chunk observed was about 476 KB.
- `npm audit --omit=dev` reported **8 production dependency advisories: 3 high and 5 moderate**, in the installed Angular dependency line. Fixed versions are available.
- No `.github` CI workflow directory exists in this working tree, despite older documentation claiming CI/CD pipelines.
- Git currently records only the initial commit. Most application directories are untracked, and a credential-shaped plaintext file is present at the repository root. Its contents were deliberately not inspected during this audit.

## Product and engineering scorecard

| Area | Assessment | What is working | Main gap |
|---|---|---|---|
| Product breadth | Strong | Most law-firm functions have usable screens and APIs | Depth and cross-module workflows vary |
| Matters and clients | Good foundation | Court fields, parties, advocates, hearings, tasks, fees, client master | Conflict checks, workflow automation, reliable court sync |
| Documents and drafting | Good foundation | Uploads, versions, locks, multilingual starter templates, rich editing, DOCX export | Malware scan, OCR/preview, governed templates and clause library |
| Knowledge and Bare Acts | Useful, still incomplete | Exact statutory text, reader, search, in-force labels, official PDFs | Amendment history, point-in-time text, wider central/state coverage |
| Research | Large corpus, mixed maturity | Structured search, full text, saved work, comparison, citations where recorded | Automated citator, semantic retrieval, acts/sections extraction for HC records |
| News | Functional | Official court/government sources, categories, source links, images | Source-health monitoring, deduplication, editorial workflow and archives |
| Billing and CRM | Functional modules | Leads, clients, invoices, payments seam, fee events | End-to-end fee-event invoicing, ledger, reconciliation and trust accounting |
| Security | Good primitives, incomplete operations | JWT, MFA, RLS, audit events, API keys, passkey/OAuth seams | Backups, secrets/KMS, malware scanning, route guards, security automation |
| Reliability and operations | High risk | Health/readiness endpoints and deployment documentation | CI, staging, restore testing, observability, release rollback |
| Automated quality | Backend foundation only | 171 collected backend tests | Full run not verified; zero frontend tests; no checked-in CI |
| UX and accessibility | Consistent visual direction | Responsive shell, shared date input, PWA, loading and empty states in many areas | Global search is inert; native dialogs remain; accessibility/mobile audit needed |
| Maintainability | Moderate risk | Modular backend and lazy frontend features | Large components, one-line templates, stale docs, unversioned source |

## What is already valuable

Preserve and strengthen these parts rather than replacing them:

- Tenant-aware backend with PostgreSQL row-level security and explicit tenant filters.
- Matter records designed for Indian courts, including CNR, court hierarchy, counsel sides, hearings, tasks, limitation dates, team assignments, and fee arrangements.
- A 5.66-million-record judgment/order corpus covering the Supreme Court and three High Courts, with structured filters and full-text enrichment work.
- Searchable Bare Acts with exact wording, a reader, official source links, and status notices.
- Firm documents, versioning, checkout, drafting templates, multilingual entry points, and DOCX export.
- Client portal, CRM, billing, notifications, audit log, webhooks, API keys, sessions, OAuth, passkeys, and tenant administration.
- Official-source legal news rather than dependence on a competing publisher.

## Material risks and gaps

### Release and recovery

1. **The working product is not safely versioned.** Almost all source directories are untracked and the branch has only the initial commit. A server or workstation failure could lose the source or make a rollback impossible.
2. **No verified database backup, point-in-time recovery, or restore drill is documented as operational.** The production database and multi-million-record corpus are the hardest assets to replace.
3. **There is no checked-in CI workflow.** Build, test, dependency audit, migration checks, and deployment safety currently depend on manual discipline.
4. **Project status documents conflict.** They cite migrations from `0037` to `0046` and several incompatible test counts, making release decisions harder.

### Security and privacy

1. The installed Angular line has current high and moderate advisories with fixes available.
2. Authenticated routes use the login guard, but the existing `permissionGuard` is not applied to feature/admin routes. APIs remain the security boundary, yet direct navigation can expose unusable or confusing screens.
3. A credential-shaped plaintext file exists in the repository root. Treat any real credential in it as compromised: rotate it, remove the file, and prevent recurrence with secret scanning.
4. Uploads lack a documented quarantine and malware-scanning pipeline.
5. DPDP-oriented export, deletion, retention, legal-hold, and consent evidence workflows are incomplete.
6. Secrets-manager/KMS integration, DAST, periodic penetration testing, and central security alerting remain outstanding.
7. Link-preview fetching needs explicit redirect and DNS-rebinding tests before it is treated as hardened SSRF protection.

### User data and workflow integrity

1. Research folders, saved items, comparisons, and alerts are stored in `localStorage`. Knowledge bookmarks and saved news are also browser-local. They do not follow the user to another device and can disappear when browser data is cleared.
2. Research alerts run only when the Research page opens; they are not scheduled server jobs and do not provide dependable delivery.
3. The top-bar “Search matters, people, judgments…” field has no search action.
4. Fee events, matter work, and invoice creation are adjacent features but not yet one controlled workflow.
5. The eCourts seam is correctly unconfigured in production because there is no official public API. Reliable sync requires a licensed source and must not be represented as live until then.

### Legal research quality

1. Citation treatment is limited to citation edges already recorded; it is not yet an automated citator.
2. High Court judgments/orders have little structured Acts and Sections coverage despite having full text available for extraction.
3. “Leading” results are a ranking heuristic, not an editorial or court-authoritative designation.
4. Fact-to-law suggestions are rules-based retrieval rather than evaluated semantic legal research.
5. The Bare Act library is useful for current wording, but only a small set has historical-version coverage. Lawyers need the text in force on the relevant date, amendments, commencement information, and authoritative source provenance.

### Quality and maintainability

1. The backend suite collects 171 tests, but a full run was not verified during this audit. Postgres-specific RLS tests also require an appropriate database role and instance.
2. The frontend has no unit, component, accessibility, or end-to-end tests.
3. Several frontend components exceed 300–600 lines and some templates are compressed into very long lines, increasing regression and review risk.
4. Native `prompt`, `alert`, and `confirm` calls remain in important flows. One native date input remains in the Act reader despite the shared Indian date component convention.
5. Research renders highlighted result markup through `innerHTML`; the trust boundary and sanitisation tests should be explicit.
6. The service worker caches `/api/v1/**`. Authenticated cache behaviour needs tests for logout, account switching, permission changes, and sensitive responses.

## Delivery principles

- Finish one end-to-end workflow before adding another isolated feature.
- Keep the backend API as the permission boundary and mirror permissions in routes for clear UX.
- Store professional work on the server with tenant/user ownership, audit events, export, and retention rules.
- Show the official source, jurisdiction, document date, ingestion date, and text status on every legal authority.
- Do not label machine-derived content as a headnote, treatment, or leading authority without a defined method and review status.
- Every production change must be reproducible from Git and reversible through a documented rollback.

## Doable backlog

Effort assumes one experienced full-stack engineer with product review. **S** is 1–3 days, **M** is 1–2 weeks, and **L** is 3–6 weeks. Infrastructure procurement and legal-data licences are excluded.

| ID | Priority | Work item | Effort | Depends on | Done when |
|---|---:|---|---:|---|---|
| REL-01 | P0 | Put the complete application under private version control | S | Repository access | All intended source/config/docs are tracked; generated files and secrets are ignored; baseline tag exists; remote backup is verified |
| SEC-01 | P0 | Rotate and remove any plaintext credentials; add secret scanning | S | REL-01 | Credential-shaped files are removed, real credentials rotated, pre-commit and CI scans block recurrence |
| OPS-01 | P0 | Automated encrypted database and object-storage backups | M | Storage destination | Daily backups and WAL/PITR retention run automatically; alerting exists; a clean-host restore is timed and documented |
| OPS-02 | P0 | Define RPO/RTO and production rollback | S | OPS-01 | Owner signs off targets; application and migration rollback runbooks are tested |
| DEP-01 | P0 | Upgrade Angular to fixed supported versions | S | REL-01 | Production audit has no known high advisory; build and smoke checks pass; PWA update behaviour is tested |
| CI-01 | P0 | Add CI for backend, frontend, migrations, lint, SCA and secret scan | M | REL-01 | Every pull request runs required checks and cannot merge on failure |
| QA-01 | P0 | Make backend tests deterministic and fast | M | CI-01 | All 171 tests complete in CI; slow/hanging tests are identified; Postgres RLS job runs separately |
| ACC-01 | P0 | Apply route-level permission guards | S | Permission matrix | Every protected route has declared permissions; direct URL tests cover allowed and denied users |
| OPS-03 | P0 | Create a staging environment from production-like configuration | M | CI-01 | Migrations, smoke tests, PWA and rollback are exercised before production deployment |
| DOC-01 | P0 | Reconcile status, security and deployment documentation | S | REL-01 | One current version/migration/test count is used; historical claims are marked as such |
| QA-02 | P1 | Add frontend smoke and end-to-end tests | M | CI-01, OPS-03 | Login, matter, document, research, billing and logout/account-switch journeys run in CI |
| OBS-01 | P1 | Central logs, error tracking, metrics and alerts | M | OPS-03 | API errors, job failures, queue lag, ingestion freshness, storage, DB and certificate alerts reach an owner |
| UX-01 | P1 | Implement working global search | M | Search API | Top bar searches matters, clients, documents, people, Bare Acts and judgments; results respect permissions |
| RES-01 | P1 | Move research workspace to server storage | M | New RLS migration | Folders, saved cases, notes, comparisons and search history sync across devices and are audited |
| RES-02 | P1 | Build scheduled research alerts | M | RES-01, worker/queue | Saved queries run on schedule, dedupe results, show history, and deliver through chosen channels |
| KNW-01 | P1 | Server-backed knowledge/news bookmarks | S | User preference model | Bookmarks sync across devices and can be exported |
| SEC-02 | P1 | Secure document ingestion | M | Object storage | MIME/content validation, quarantine, malware scan, size limits and audit events run before availability |
| SEC-03 | P1 | Complete SSRF and HTML trust-boundary tests | S | CI-01 | Redirects, private/reserved IPs, DNS rebinding and highlighted markup are covered by tests |
| UX-02 | P1 | Replace native dialogs and remaining native date input | S | Shared dialog patterns | No core flow uses browser prompt/alert/confirm; dates display and parse day-first consistently |
| UX-03 | P1 | Accessibility and responsive audit | M | QA-02 | Keyboard navigation, focus, labels, contrast, zoom and mobile layouts meet agreed WCAG 2.2 AA checks |
| SRV-01 | P1 | Verify PWA cache isolation | S | QA-02 | Logout/account switching cannot reveal cached tenant data; sensitive API responses have an explicit cache policy |
| NEWS-01 | P1 | News ingestion control room | M | OBS-01 | Source freshness, failures, duplicates, image status and manual review are visible; stale sources alert |
| LAW-01 | P1 | Extract Acts and Sections from High Court full text | M | Corpus job capacity | Measured precision/recall sample is accepted; filters populate incrementally with checkpoints |
| MAT-01 | P2 | Matter workflow and limitation rules | L | Rule catalogue review | Practice-specific checklists create tasks/deadlines with source, override reason and audit history |
| MAT-02 | P2 | Conflict check | M | Clean client/party/counsel identities | New matter/client intake checks names and relationships and records clearance |
| BILL-01 | P2 | Connect fee events to draft invoices | M | Accounting rules | Eligible events become reviewable invoice lines without duplicates; audit trail links matter to invoice |
| BILL-02 | P2 | Ledger, receipts and reconciliation | L | BILL-01, payment provider | Payments, refunds, GST/TDS/RCM and outstanding balances reconcile with exports |
| DRAFT-01 | P2 | Governed template and clause library | L | Role/approval rules | Templates have owners, versions, approval status, jurisdiction/language, variables and usage history |
| DRAFT-02 | P2 | Court-format packs and translation review | M | DRAFT-01 | English/Hindi/Punjabi outputs use reviewed terminology and court-specific page/filing conventions |
| PORTAL-01 | P2 | Complete client collaboration | M | Notification reliability | Secure messages, document requests, approvals, appointment and invoice views are one timeline |
| LAW-02 | P2 | Bare Act provenance and amendment pipeline | L | Official-source catalogue | Every provision has source, effective dates, amendment links and last-verified date |
| LAW-03 | P2 | Point-in-time statute reader | L | LAW-02 | User selects a date and sees text then in force, with changes highlighted and citation-ready URL |
| RES-03 | P2 | Automated citation extraction and citator foundation | L | Full text, evaluation set | Citations are extracted with measured accuracy; treatment claims show evidence and confidence/review state |
| RES-04 | P2 | Research memo collaboration and exports | M | RES-01 | Teams share source-linked notes, pin quotations, cite paragraphs and export a reproducible memo |
| DATA-01 | P2 | Legal-data provenance dashboard | M | OBS-01 | Coverage, licence, source, ingestion date, text availability and extraction quality are visible per court/source |
| AI-01 | P3 | Evaluated semantic legal retrieval | L | LAW-01, RES-03, DATA-01 | Benchmarked hybrid search beats keyword baseline on a reviewed Indian-law query set and always links sources |
| AI-02 | P3 | Source-grounded summaries and drafting assistance | L | AI-01, audit controls | Generated statements cite passages; prompt/output audit, redaction, feedback and abstention rules are live |
| INT-01 | P3 | Licensed eCourts/cause-list connector | L | Commercial/legal agreement | Import/refresh works under provider terms, maps source fields, records freshness and never overwrites firm work |
| PRIV-01 | P3 | DPDP rights and retention workflows | L | Data inventory and counsel review | Export, correction, deletion, retention, legal hold and consent evidence are operational and audited |
| SCALE-01 | P4 | Expand court and statutory coverage | L | Capacity and licence plan | Coverage expands by an approved priority list with storage, indexing, quality and freshness budgets |
| DR-01 | P4 | High-availability and disaster recovery programme | L | OPS-01/02 | Failure drills meet RPO/RTO; DNS, database, storage and application single points are addressed |

## Recommended roadmap

### Sprint 0: first 7 days — protect the asset

- Complete REL-01 and SEC-01. Do not begin another large feature until the source is safely versioned.
- Patch Angular dependencies under DEP-01 and rebuild the production bundle.
- Write the backup destination, retention, RPO, RTO, and restore procedure; start OPS-01.
- Create a simple permission matrix for every route and API domain.
- Reconcile migration/test/version claims and designate this document as the planning source.

**Exit gate:** a recoverable Git baseline exists, exposed credentials are rotated, no known high production dependency advisory remains, and the first automated backup has completed.

### Days 8–30 — make every release verifiable

- Deliver CI-01, QA-01, ACC-01 and OPS-03.
- Run the full backend suite in CI and a separate real-Postgres RLS job.
- Add six critical frontend journeys: login/session refresh, role-denied route, matter creation/update, document upload/download, research/open authority, and billing/payment mock.
- Perform and record the first database restore drill.
- Add baseline logs and alerts for 5xx rate, database/storage health, ingestion jobs, backup failure and certificate expiry.

**Exit gate:** a pull request can move through CI to staging and production with a tested rollback, and a backup can restore to a clean environment.

### Days 31–60 — preserve user work and simplify navigation

- Deliver UX-01, RES-01, RES-02 and KNW-01.
- Replace browser-only research alerts with scheduled jobs and notification delivery.
- Complete upload scanning and the PWA cache-isolation tests.
- Replace native dialogs/dates and conduct the accessibility/mobile pass.
- Launch the news ingestion control room.

**Exit gate:** a lawyer can change device without losing saved research, bookmarks, comparisons or alerts; global search reaches the main records.

### Days 61–90 — complete daily law-firm workflows

- Start MAT-01, MAT-02, BILL-01 and DRAFT-01.
- Connect matter work and fee events to reviewed invoice drafts.
- Add conflict clearance at intake.
- Introduce governed templates and clause reuse, then add court-format and language review.
- Expand portal collaboration around documents, approvals and invoices.

**Exit gate:** client intake, conflict clearance, matter work, drafting, fee capture, invoice review and client approval form one traceable workflow.

### Months 4–6 — build legal authority, not just content volume

- Deliver LAW-01, LAW-02, LAW-03, RES-03 and DATA-01.
- Extract Acts/Sections from High Court full text with a labelled evaluation sample.
- Add amendment/effective-date models and point-in-time statute reading.
- Build citation extraction and treatment evidence before calling the result a citator.
- Expand sources only where provenance, licence, ingestion health and text quality can be shown.

**Exit gate:** users can verify why a result appears, quote stable statutory/case paragraphs, and identify the text that applied on the relevant date.

### Months 7–12 — differentiated intelligence and scale

- Deliver AI-01 and AI-02 only after the legal retrieval evaluation gate passes.
- Add the licensed court connector if a lawful source agreement is available.
- Complete privacy/retention workflows and formal security testing.
- Expand courts and Acts according to user demand and capacity economics.
- Remove infrastructure single points and run disaster-recovery exercises.

## Suggested team ownership

| Workstream | Primary owner | Review needed |
|---|---|---|
| Release, CI, backups, staging, observability | Platform/backend engineer | Security and product owner |
| Permissions, privacy, audit, upload security | Security-minded backend engineer | Indian privacy/legal counsel |
| Matters, clients, billing and portal | Product full-stack engineer | Practising lawyer and accountant |
| Research, Bare Acts, news and corpus | Legal-data engineer | Legal research editor |
| UX, accessibility, global search and PWA | Frontend engineer/designer | Lawyer usability group |
| AI retrieval and drafting | Search/ML engineer | Legal-data engineer and legal reviewers |

At least one practising litigator, one district-court practitioner, and one firm administrator should review acceptance samples monthly. Their review should use real anonymised tasks: finding the applicable provision, checking historical wording, preparing a filing, calculating a limitation date, opening a matter, and raising an invoice.

## Measures to track

Track these from the first month so progress is visible:

- Release frequency, failed deployment rate, rollback time and mean time to recovery.
- Backup success rate, last successful restore, measured RPO and RTO.
- Test duration, flaky-test rate, escaped defects and frontend critical-journey pass rate.
- 5xx rate, p95 search/API latency, ingestion delay, job failures and source freshness.
- Search success: result opened, reformulation rate, zero-result rate and source verification clicks.
- Research quality: citation extraction precision/recall, statute-version accuracy and reviewed treatment accuracy.
- Workflow completion: intake-to-open time, overdue tasks, fee-event-to-invoice time and invoice collection time.
- User trust: saved-work recovery, alert usefulness, corrections reported and source/provenance coverage.

## Explicitly deferred until prerequisites exist

- Do not scrape CAPTCHA-gated court systems or present the eCourts seam as live without a licensed connector.
- Do not expand to every High Court merely because ingestion code exists; storage, extraction, monitoring and user demand must justify the next source.
- Do not market semantic search, AI headnotes, citator treatment, or outcome analytics until each has a labelled evaluation set and visible source evidence.
- Do not add native mobile applications before the responsive PWA, offline policy, upload security and critical web journeys are dependable.

## Next decision checkpoint

After the 30-day exit gate, review actual incident, usage and search data. Re-estimate the 60- and 90-day backlog, keep no more than two large product initiatives active at once, and require every new feature to identify the existing workflow it completes.

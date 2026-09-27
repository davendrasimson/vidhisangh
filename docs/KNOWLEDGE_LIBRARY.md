# Knowledge library

The Knowledge page has two collections: an editorial Acts guide catalogue and the tenant-scoped firm library.

## Acts explained

`frontend/src/app/features/knowledge/data/acts.ts` holds 25 introductory guides. Each has an official India Code source, an everyday example, selected provisions, preparation prompts, applicability notes and related guides. Search includes the full title, abbreviation, topic, everyday keywords and selected provision references. `?act=ipc` and other guide IDs can be bookmarked or shared.

This is not a complete statute corpus, a consolidated amendment service, or a section-by-section commentary. The edition date is an editorial edition date, not certification of legal currency or lawyer review. The guides make no automatic decision about applicable law. IPC, CrPC and the Evidence Act are marked repealed with savings; the criminal-law transition links to the Government's commencement explanation. State rules, notifications, exceptions and subsequent amendments require checking before action. Official links were located through India Code; its server intermittently timed out during direct retrieval.

To add coverage, create a guide using the same structure, confirm the enactment and selected provisions from official legislation, add meaningful everyday search phrases, and update related references. Do not label a Bill as an enacted Act, infer commencement from assent, or present old/new section numbers as interchangeable. Run `node scripts/test-knowledge.cjs` from `frontend`.

## Firm resources

Existing knowledge CRUD now exposes editing in the UI, source URLs, optional firm-entered review dates and document attachments. Migration `0041_knowledge_resources` adds nullable `source_url`, nullable `reviewed_on` and an empty-default JSON list of attachment UUIDs. Attachment IDs are checked against live documents in the same tenant on create/update. Downloads retain document permission checks. Uploads stay in Documents if an editor is cancelled or a resource link is removed.

Bookmarks store resource IDs only, in localStorage under the user and tenant IDs. They do not sync across browsers. The reader shows recorded dates, never an inferred approval badge.

“Use in a matter” loads active matters. Templates recognise `{{placeholder_name}}`, prefill client/matter fields, and create a separate text document associated with the chosen matter using the existing document-upload API. The user can edit and preview before saving. Checklist bullet/numbered lines create tasks through the existing task API. Confirmed task successes are tracked so retry resumes after them; an ambiguous network failure still requires checking the matter. The upload API validates that the destination matter belongs to the same tenant. Original knowledge content is not modified. Attachments are not automatically copied with drafts.

Version history, review/approval workflows, archive/restore, synced bookmarks, DOCX rendering, AI answers and exhaustive legislation ingestion remain separate follow-ups.

## Verification

- `node scripts/test-knowledge.cjs`: guide integrity, search, legacy labels, placeholders, checklist parsing.
- `.venv-linux/bin/pytest tests/test_knowledge.py tests/test_documents.py -q`: CRUD, partial metadata updates, URL/date validation, attachment tenant isolation and document regression checks and matter placement isolation.
- Angular production build; local browser checks with mock API data cover reader, deep links, bookmarks, resource editing, draft creation, checklist creation and mobile layout.

## Deployment — 25 September 2026

Deployed migration `0041_knowledge_resources`, the Knowledge backend and the document matter-placement check, followed by the production frontend. The shared navigation now becomes an overlay on small screens so the Knowledge reader remains usable on mobile. Nine Knowledge/document tests and the catalogue/helper checks passed; desktop and mobile browser workflows passed with mock API data. Production readiness reported database and Redis healthy. Previous code and frontend entry files are backed up at `/opt/vidhisangh/pre-knowledge-FqZTA6SR/code-and-entrypoints.tar.gz`; older hashed frontend assets were retained.

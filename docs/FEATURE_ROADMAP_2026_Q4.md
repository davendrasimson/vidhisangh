# Feature roadmap — Q4 2026

**Reviewed:** 27 September 2026  
**Scope:** user-facing capability and cross-module workflow. Security and infrastructure work are tracked separately.

## Product position

VidhiSangh already has broad coverage: CRM, clients, matters, court data, hearings, tasks, drafting, documents, billing, payments, a portal, research, Bare Acts, knowledge, news, networking, marketplace and administration. The first feature-integration release connected the most important records around a matter. The next gains come from completing the daily legal-work journey and moving browser-only work to durable, shared records.

## Ordered roadmap

| Order | Outcome | Deliverable | Why now | Acceptance measure | Estimate |
|---:|---|---|---|---|---:|
| 1 | One place to start the day | **Today / action inbox** combining hearings, limitation dates, overdue tasks, approvals, client replies and unbilled fee events; working global search across matters, clients, documents, people, judgments, Acts and knowledge | Users still visit separate modules to discover urgent work; the shell search is currently inert | A lawyer can find any core record and clear the day's urgent work without checking each module | 2–3 weeks |
| 2 | Complete matter collaboration | **Matter timeline + client portal** with client uploads, document requests, secure matter messages, hearing acknowledgement, invoice/payment status and approval reminders | The matter is now the hub, but portal interaction remains mostly one-way | Every client request, response, document, approval and payment is visible on the matter timeline | 3–4 weeks |
| 3 | Hearing-to-next-action workflow | Structured directions/order upload, next date, responsible person, deadline generation, fee event and client update; court holiday and recurring calendar support | Hearing preparation exists, but post-hearing work is still split across screens | Recording one hearing outcome produces all selected follow-up records once, with an audit trail | 2–3 weeks |
| 4 | Production-grade drafting | Governed template and clause library with owner, jurisdiction, court, language, version, approval status and matter-field merge; court-format packs for English, Hindi and Punjabi | Drafting is useful now, but firms need controlled reusable language and known versions | A reviewed template produces a matter-linked draft with provenance and no unresolved fields | 4–6 weeks |
| 5 | Complete matter finance | Time entries, expenses/court fees, retainers, recurring invoices, receipts/credit notes, GST/TDS/RCM reconciliation and matter profitability | Fee-event invoicing is connected; accounting depth and leakage control remain | All billable work reaches a draft invoice or an explicit write-off, and matter margin is explainable | 4–6 weeks |
| 6 | Durable legal research workspace | Move folders, saved authorities, notes, comparisons and alerts from browser storage to tenant/user storage; add team sharing, scheduled alerts and citation-ready memo export | Current saved research can be lost with browser data and does not follow the user across devices | Saved work syncs across devices, alerts run without opening the page, and exports retain sources/paragraphs | 3–5 weeks |
| 7 | Research confidence layer | Citation extraction, later-treatment evidence, similar-case retrieval, Acts/Sections extraction from High Court text, and date-effective statutory text | Corpus size is strong; lawyers need authority status, provenance and text applicable on the relevant date | Every treatment claim links to the paragraph supporting it; statute reader can show text for a selected date | 6–10 weeks, incremental |
| 8 | Firm intelligence and mobility | Workload/capacity, source-to-revenue, matter-stage duration, profitability and court/judge trend dashboards; installable mobile workflows for scan/upload, offline notes and quick hearing updates | These become useful after the underlying workflows produce consistent server-side data | Management can drill from a metric to source records; core hearing/document actions work well on a phone | 4–8 weeks |

## Release sequence

### Release 1 — Find and act (weeks 1–3)

- Implement a permission-filtered unified-search API and result palette.
- Replace the decorative shell search with keyboard-accessible grouped results.
- Add the Today queue, owner filters, snooze and direct completion actions.
- Feed existing matter, calendar, portal, notification and fee-event records into the queue without duplicating them.

### Release 2 — Matter collaboration (weeks 4–7)

- Add one chronological matter timeline with typed entries and source links.
- Add client document requests/uploads and matter-scoped secure messages.
- Add portal invoice/payment state and reminders.
- Extend the hearing outcome form to create reviewed follow-up actions atomically.

### Release 3 — Drafting and finance (weeks 8–13)

- Add template/clause versions, review status and role-based publishing.
- Add court/jurisdiction/language metadata and reviewed translations.
- Add time and expense capture from a matter and hearing.
- Add retainers, receipts, adjustments and profitability views.

### Release 4 — Research depth (weeks 14–22)

- Persist the research workspace and bookmarks on the server with RLS and audit history.
- Schedule research and legal-change alerts with deduplication and delivery history.
- Build citation/statute extraction against a lawyer-reviewed evaluation set.
- Add amendment chronology and point-in-time text Act by Act, starting with BNS/BNSS/BSA, IPC/CrPC/Evidence Act, CPC, Companies Act and Constitution.

## Synchronisation rules

1. `matter_id` and `client_id` travel through drafting, documents, research, hearings, fees, invoices, portal records and messages.
2. A module creates one source record; Today, timelines and analytics reference it rather than copying it.
3. Automated actions are idempotent. Repeating hearing completion, invoice preparation or an alert cannot create duplicates.
4. Every legal excerpt retains source URL/document, court or legislature, date, paragraph/section and verification state.
5. User work is stored server-side when it must survive a browser change or be shared with a team.
6. Analytics drill down to the records used to calculate the number.

## Items deliberately waiting on external inputs

- Licensed eCourts/cause-list integration.
- Expansion of the court-order PDF corpus until the planned object store is available.
- Live payment, SMS, WhatsApp, Google and Microsoft integrations until owner accounts and credentials are selected.
- AI drafting or summaries until retrieval quality, source citation and a reviewed evaluation set are measurable.


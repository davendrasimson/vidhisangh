# VidhiSangh feature integration audit

**Audit date:** 27 September 2026  
**Focus:** product features, workflow continuity, reuse of features already built, and synchronization between modules. Security and infrastructure work are intentionally outside this roadmap.

## Delivered integration baseline — 27 September 2026

The first connected slice of items 1–8 is live in production on migration `0047_feature_integration`:

1. **Matter command centre:** direct, context-preserving actions for matter documents, drafts, research, Bare Acts, billing, portal and marketplace staffing.
2. **CRM conversion:** conversion now reuses a matching client or creates a Client master record, links it to the new matter, and carries the assigned lawyer.
3. **Research binder:** exact judgment paragraphs and statutory provisions are stored as structured, source-linked matter authorities and displayed on the matter.
4. **Matter-aware drafting:** documents and drafts opened from a matter retain both matter and client links and prefill the available matter/client template context.
5. **Fees to invoices:** all or selected unbilled fee events can create a linked draft invoice atomically; the invoice uses the Client link and GST/RCM default.
6. **Hearing workflow:** scheduled hearings can create a deduplicated four-step preparation pack; existing hearing completion continues to raise configured fee events.
7. **Client 360 and portal:** Client shows matter, document, invoice/outstanding and KYC/portal summaries; the client portal now displays linked invoices. Portal sharing refuses documents filed to another matter.
8. **Network/marketplace staffing:** a marketplace request can carry a matter; accepting a response closes the listing and adds the responder as counsel on that matter.

This is an integration baseline, not the final depth described later in the roadmap. Conflict clearance, matter-specific secure conversations, client uploads, detailed hearing directions, time entries, template-version provenance and matter profitability remain later increments.

## Product conclusion

VidhiSangh already contains most of the individual building blocks required by a litigation and law-firm platform. The primary feature problem is that several modules behave like separate applications. Users must reselect a client, re-enter names, manually copy research, manually prepare invoice lines, and move between navigation items without a shared matter context.

The best next product move is to make the **matter the working hub**. Client, court record, team, tasks, hearings, research, statutory provisions, drafts, documents, fees, invoices, portal activity, and communications should all remain attached to the same matter. The existing database already supports several of these links; many improvements require orchestration and UI rather than an entirely new subsystem.

## Current synchronization map

Legend: **Connected** means the data and user flow are joined; **Partial** means a link or one-way action exists; **Separate** means the features operate independently.

| From | To | Status | Current behaviour | Missing handoff |
|---|---|---|---|---|
| CRM lead | Matter | Partial | A won lead can create and open a matter | Conversion uses the lead name as free-text client; it does not create/link a Client or carry contact, referral, estimated value, activities or assignment |
| Client | Matter | Connected | Client page lists matters and can start a matter for that client | Add a consolidated client activity and financial view |
| Client | Documents/drafts | Partial | Documents and drafts can carry `client_id`; client deep links can filter Documents | Client page does not show documents/drafts; a user can still create unlinked work |
| Client | Billing | Separate | Invoice stores only a client-name snapshot | Invoice has no `client_id`; client tax/KYC defaults are not applied by the current invoice form |
| Matter | Calendar | Connected | Agenda combines standalone events, hearings, task deadlines and limitation dates | Add hearing-preparation state and calendar-to-matter quick actions |
| Matter | Documents | Data-ready, UI partial | Document and folder models support `matter_id`; portal can list matter documents | Matter page has no document panel/quick action; Documents page is primarily client-oriented |
| Matter | Drafting | Data-ready, UI partial | Draft model/API supports `matter_id` and `client_id` | Drafts started from Documents only pass the client; matter facts, parties, court and sections do not prefill templates |
| Matter | Research | Partial | A judgment paragraph can be saved into a matter note | No matter research binder, issue list, authority table, citation status or direct “research this issue” flow |
| Matter | Bare Acts | Partial | A statutory section can be saved into a matter note | Matter Acts/Sections are not deep links to the reader; saved law is unstructured text rather than a pinned authority |
| Firm Knowledge | Matter | Connected | Templates/notes create matter drafts; checklists create matter tasks | Result should open in the common drafting workspace and retain template version/source |
| Matter fee terms | Fee events | Connected | Milestones, hearing results and manual charges create fee events | Hourly work/time entries are absent |
| Fee events | Invoice | Separate | Events explicitly anticipate invoicing and contain `invoice_id` | No action converts selected unbilled events into invoice lines or updates them atomically to invoiced |
| Matter | Billing | Partial | Invoice API supports `matter_id` | Billing UI creates invoices without selecting a matter and manually asks for client name/tax rate |
| Billing | Payments | Connected | Invoice payment and reconciliation are implemented | Add receipts, adjustments and client/matter financial timeline |
| Matter | Client portal | Connected, limited | Updates, approval requests and selected documents are shared | Portal lacks invoice/payment view, secure requests/messages, hearing acknowledgement and client-uploaded documents |
| Documents | Portal | Connected with a validation gap | A selected document can be shared and downloaded | Sharing should verify that the document belongs to the same matter, or explicitly record a cross-matter exception |
| Matter | Notifications | Partial | Team assignment and some matter events notify users | Tasks, deadlines, hearings, limitation dates, fee events, approvals and portal responses do not form one notification policy |
| Matters/CRM/Billing | Analytics | Partial | Dashboard aggregates invoices, matter counts, pipeline, tasks and hearings | No matter/client profitability, fee leakage, workload, source-to-revenue or stage-duration analysis |
| Professional network | Messaging | Connected | Users can open direct conversations from profiles | Conversation has no matter context, filing, task or document-reference mechanism |
| Marketplace | Matter/team | Separate | Firms can post and receive responses for local counsel, experts and referrals | Accepted response cannot create an external collaborator, matter role, conflict check, engagement or tracked fee |
| Groups/network | Knowledge | Separate | Communities and firm pages publish discussions | Useful posts cannot be promoted into reviewed firm knowledge or linked to research/matters |
| Legal news | Research/matter | Separate | News can be searched, filtered, saved locally and opened at source | No follow topic/court/Act, create research alert, attach to matter, or convert notification into a research item |
| Dashboard | Daily work | Partial | Shows broad counts and links to modules | It does not show “what needs my action today” across hearings, tasks, limitation, approvals, drafts and unbilled work |
| Global navigation | All records | Separate | The top search box is visible | It has no search action or cross-module result page |

## Features that can be leveraged immediately

### 1. Turn the matter page into a command centre

The matter already owns most operational data. Add a compact tabbed workspace:

- **Overview:** court record, status, stage, team, next hearing and limitation.
- **Work:** tasks, hearing preparation, chronology and timeline.
- **Research:** pinned judgments, statutory sections, legal issues and notes.
- **Drafts & documents:** matter-filtered drafts, uploaded documents and filing status.
- **Fees & invoices:** fee arrangement, unbilled events, invoice history and collections.
- **Client & portal:** client record, KYC state, approvals, shared documents and updates.

Use the existing APIs and `matter_id` fields first. A single matter summary endpoint can follow after the UI establishes what information is actually needed together.

### 2. Complete lead-to-client-to-matter intake

The current CRM conversion skips the client master. Replace the single “convert to matter” action with a short conversion review:

1. Match an existing client by email/mobile/name or create a new Client.
2. Carry contact details, practice area, referral source, notes and responsible lawyer.
3. Run conflict clearance and request KYC/consent where required.
4. Select an engagement-letter template and fee proposal.
5. Create the matter with the linked client and preserve the original lead relationship.

This leverages CRM, Clients, KYC, Knowledge templates, Drafting, Matters, Team and Fee Arrangements in one workflow.

### 3. Build a matter research binder

Research and Bare Acts already send excerpts to matter notes. Replace that text-only handoff with structured pinned authorities:

- judgment ID, citation, paragraph number, quotation and source URL;
- Act, section, version/effective date and exact wording;
- issue or proposition for which the authority is saved;
- treatment/status, verification date and researcher note;
- favourable, adverse, distinguish, background or pending-review label.

The matter can then produce an authority table, case note, list of citations and research memo without losing source links.

### 4. Prefill drafting from the matter

Drafting templates should receive a standard matter context containing client, parties, cause title, court, case/CNR, counsel, dates, Acts, Sections, chronology and selected relief. Starting “Draft from this matter” should:

1. Open the chosen English/Hindi/Punjabi template.
2. Fill known values while visibly leaving unknown fields incomplete.
3. Attach the new draft to both matter and client.
4. Let the user insert pinned statutory sections and judgment quotations with citations.
5. File the final DOCX/PDF into the matter documents and optionally send it for portal approval.

Most of the data and editor capability already exist; the missing part is a shared placeholder contract and matter-aware entry point.

### 5. Generate invoices from fee events

The matters module already produces structured fee events, and each event already has an invoice placeholder. Add “Prepare invoice” to a matter:

- select unbilled events;
- group or keep separate invoice lines;
- use linked Client tax/GST/TDS defaults;
- preview issue date, due date, notes and totals;
- create one draft invoice and mark all selected events invoiced in the same transaction;
- show invoice/payment state in the matter and client timelines.

This is the highest-value unfinished synchronization because it connects work performed to money collected.

### 6. Add hearing preparation and post-hearing flows

Combine Calendar, Matter, Knowledge checklists, Documents and Fee Events:

- **Before hearing:** preparation checklist, required documents, brief, authorities, responsible team member and reminder schedule.
- **At/after hearing:** record appearance, purpose, order/outcome, next date and directions.
- **Automatic follow-up:** create directed tasks, update the calendar, raise applicable hearing fees, save the order, and prepare a client portal update.

The current hearing status and fee-event triggers provide much of the backend foundation.

### 7. Create a client 360-degree workspace

Expand the client page beyond KYC and matter list. Show:

- active/closed matters and next important dates;
- drafts/documents grouped by matter;
- invoices, receipts, outstanding amount and tax treatment;
- portal links and pending approvals;
- communications and requested documents;
- conflict relationships, referrals and engagement history.

The client becomes the commercial relationship view, while the matter remains the legal-work view.

### 8. Use the professional network for matter staffing

Network, Marketplace, Messaging and profiles are currently valuable but separate from practice work. Add a controlled path:

1. Post a local-counsel/expert/research request from a matter with only approved non-confidential details.
2. Review responders using profiles and prior firm history.
3. Accept a responder into an external matter role after conflict/terms review.
4. Open a matter-linked conversation and share selected documents.
5. Track agreed rate, work request, deliverable and payment status.

This makes the network commercially useful rather than a standalone social layer.

### 9. Create a knowledge feedback loop

Firm Knowledge already applies checklists and templates to matters. Add the reverse flow:

- promote a successful matter checklist, argument structure or draft into a proposed firm resource;
- strip client data before submission;
- require reviewer approval and a review date;
- preserve the source matter internally for provenance;
- track which template version produced each draft and which resources lawyers actually reuse.

This lets the library improve from completed work rather than relying only on manual authoring.

### 10. Turn news into monitored legal change

News should support “Follow” actions for a court, Act, regulator, subject or saved query. A followed item can:

- appear in a lawyer’s update inbox;
- be attached to a matter or firm knowledge note;
- start a research query using extracted court/Act/section terms;
- create a review task when a legal change affects a tagged template or active matter.

This uses the existing news, notifications, Knowledge, Research and Matters features.

## Feature-first delivery order

### Release A — connected matter workspace, 1–2 weeks

| Item | Scope | Reuse |
|---|---|---|
| Matter quick actions | Research issue, open Bare Act, create draft, upload document, prepare invoice, portal update | Existing routes and APIs |
| Matter documents panel | List/upload/filter using existing `matter_id` | Documents API |
| Matter drafts panel | Create/list drafts with both `matter_id` and `client_id` | Drafting API/editor |
| Acts and Sections links | Open Knowledge reader with Act/Section query | Bare Act reader |
| Billing deep link | Open invoice creation with matter/client context | Invoice API |

**Acceptance:** a user can start from one matter and reach every related work area without re-entering the matter or client.

### Release B — intake synchronization, 2 weeks

| Item | Scope | Reuse |
|---|---|---|
| Conversion review | Find/create Client before creating Matter | CRM, Clients |
| Carry intake data | Contact, source, notes, practice area, responsible lawyer | Existing lead/client fields |
| Engagement start | Apply KYC, conflict status, engagement draft and fee arrangement | KYC, Knowledge, Drafting, Matters |
| Client 360 first cut | Matters, documents and invoices summary | Existing list APIs plus billing client link |

**Acceptance:** one conversion produces a linked client and matter without duplicate typing and retains the original lead attribution.

### Release C — fees to invoices, 1–2 weeks

| Item | Scope | Reuse |
|---|---|---|
| Add invoice `client_id` | Preserve client link and snapshot billing name/address/tax fields | Clients, Billing |
| Prepare from events | Select unbilled fee events and create lines | Matter fee events |
| Atomic linkage | Invoice creation and event status update succeed or fail together | Existing `invoice_id` field |
| Matter/client money view | Draft, sent, overdue, paid, balance and receipts | Billing, Payments |

**Acceptance:** a hearing or milestone can become a correctly linked draft invoice in under one minute, with no duplicate billing.

### Release D — matter research binder and citation-aware drafting, 2–3 weeks

| Item | Scope | Reuse |
|---|---|---|
| Pinned authority model | Judgments, paragraphs, Acts, Sections and propositions | Research, Knowledge |
| Matter research tab | Issues, favourable/adverse authorities, notes and verification | Matter workspace |
| Draft insertion | Insert quotation/statutory text with source and citation | Rich editor |
| Memo/authority export | Produce reusable research memo and list of authorities | DOCX export |

**Acceptance:** every legal proposition saved to a matter retains a clickable source and can be inserted into a draft or exported memo.

### Release E — hearing and client collaboration, 2–3 weeks

| Item | Scope | Reuse |
|---|---|---|
| Hearing preparation pack | Checklist, documents, authorities, assignee and reminders | Matters, Knowledge, Documents |
| Outcome workflow | Order, next date, directions, tasks, fee event and portal-update draft | Hearings, Calendar, Fees, Portal |
| Portal expansion | Invoice view, document request/upload and matter messages | Portal, Billing, Documents, Messaging patterns |
| Action inbox | Pending approvals, overdue tasks, hearings, limitations and unbilled events | Dashboard, Notifications |

**Acceptance:** recording a hearing outcome creates the agreed follow-up work and client update without visits to multiple independent screens.

### Release F — network and knowledge leverage, 3–4 weeks

| Item | Scope | Reuse |
|---|---|---|
| Matter-based marketplace request | Post approved brief for local counsel/expert/researcher | Marketplace |
| External collaborator record | Terms, role, selected files, communication and deliverable | Profiles, Messaging, Documents |
| Promote work to knowledge | Anonymise and submit matter work for firm review | Knowledge, Drafting |
| Legal-change watchlist | Follow sources/topics and attach relevant news to matters/resources | News, Notifications, Research |

**Acceptance:** network engagement and completed matter work feed back into live matters and the firm library.

## Immediate implementation backlog

These tasks give the fastest improvement without waiting for the larger releases:

1. Add Documents, Drafts, Research and Billing quick actions to the matter header.
2. Pass `matter_id` and `client_id` when starting any draft from a matter.
3. Add `matter_id` query support to the Documents page and preserve it while uploading or filing drafts.
4. Link matter Act/Section chips to the exact Bare Act search/reader.
5. Add a “Research this matter” action that preloads cause title, court, Acts, Sections and advocates.
6. Add `client_id` to invoices and prefill client GST/TDS/place-of-supply defaults.
7. Add “Prepare invoice” for selected unbilled matter fee events.
8. Change CRM conversion to link or create a Client before creating the Matter.
9. Show documents, invoices and pending portal actions on the Client page.
10. Enforce same-matter document sharing in the portal or require an explicit exception.
11. Add reminders/notifications for limitation, tasks, hearings, portal responses and unbilled events.
12. Replace the dashboard counts with a prioritised “My work today” queue.

## Features to consolidate rather than expand

- **Documents and Drafting:** keep one workspace, but allow entry from Client and Matter with context preserved.
- **Matter notes, research notes and saved excerpts:** use one structured matter-research model instead of adding more kinds of free-text notes.
- **Calendar deadlines, matter tasks and reminders:** show them through one action queue while preserving their source records.
- **Network messages and future portal messages:** reuse a common conversation pattern, but keep permissions and audiences distinct.
- **Knowledge starter templates and editable firm resources:** starter content should be copied into governed firm resources before extensive customization.
- **Dashboard and Analytics:** dashboard should drive today’s action; Analytics should answer management and profitability questions.

## Recommended product navigation

Keep the main navigation simple and group existing features by job:

- **Today:** dashboard/action inbox, calendar and notifications.
- **Practice:** clients, matters, documents/drafting, billing and CRM.
- **Law:** research, Bare Acts, legal news and firm knowledge.
- **People:** messages, professional network, groups and marketplace.
- **Manage:** analytics, team/rates, settings and administration.

Global search should sit above these groups and return permission-filtered results grouped as Matters, Clients, Documents, People, Judgments, Bare Acts and Knowledge.

## Product outcome to target

A lawyer should be able to perform this complete journey without retyping context:

1. Convert a lead into a verified client and linked matter.
2. See the next deadline and prepare the matter checklist.
3. Research the issue, pin the exact statutory text and judgment paragraphs.
4. Draft a pleading using matter data and cited authorities.
5. File the document, share it for approval and prepare the hearing.
6. Record the hearing outcome, create follow-up tasks and inform the client.
7. Convert the hearing or milestone fee into an invoice and reconcile payment.
8. Promote the reusable checklist or drafting pattern into the firm library.

That connected journey should take priority over adding more standalone modules.

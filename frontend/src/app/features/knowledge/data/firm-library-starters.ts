import { KnowledgeCategory, KnowledgeItem } from '@core/models/knowledge.models';

const REVIEWED = '2026-09-26';
const CREATED = '2026-09-26T00:00:00Z';

function starter(
  id: string,
  title: string,
  category: KnowledgeCategory,
  practiceArea: string,
  tags: string[],
  body: string,
  sourceUrl: string | null = null,
): KnowledgeItem {
  return {
    id: `starter-${id}`,
    title,
    category,
    practice_area: practiceArea,
    tags: [...tags, 'English', 'India'],
    body,
    source_url: sourceUrl,
    reviewed_on: REVIEWED,
    attachments: [],
    created_by: 'VidhiSangh starter library',
    created_at: CREATED,
    updated_at: CREATED,
  };
}

const templates: KnowledgeItem[] = [
  starter('tpl-matter-brief', 'Client matter brief', 'template', 'General practice', ['Intake', 'Matter management'], `CLIENT MATTER BRIEF

Client: {{client_name}}
Matter: {{matter_title}}
Reference: {{matter_number}}

1. Client's objective
{{client_objective}}

2. Material facts and chronology
{{material_facts}}

3. Opposing parties and relationships
{{parties}}

4. Documents received and documents required
{{documents}}

5. Possible laws, forum and limitation issues
{{initial_issues}}

6. Immediate action and responsible lawyer
{{next_steps}}

Review note: Record disputed facts separately. Verify every date and legal proposition before advice is issued.`),
  starter('tpl-chronology', 'Case chronology and event table', 'template', 'Litigation', ['Chronology', 'Evidence'], `CASE CHRONOLOGY

Matter: {{matter_title}}
Prepared for: {{client_name}}
Cut-off date: {{cut_off_date}}

DATE | EVENT | PERSON / DOCUMENT | ADMITTED OR DISPUTED | LEGAL SIGNIFICANCE
{{chronology_rows}}

Missing periods or conflicting dates
{{date_gaps}}

Limitation trigger dates to verify
{{limitation_dates}}

Next verification steps
{{next_steps}}`),
  starter('tpl-research-memo', 'Legal research memorandum', 'template', 'Research', ['Research', 'Authorities'], `LEGAL RESEARCH MEMORANDUM

Question presented
{{question}}

Short answer
{{short_answer}}

Material facts and assumptions
{{facts}}

Applicable legislation
{{legislation}}

Binding authorities
{{binding_authorities}}

Persuasive authorities
{{persuasive_authorities}}

Analysis, counterarguments and factual dependencies
{{analysis}}

Conclusion and recommended next research
{{conclusion}}

Source check: Record court, date, neutral citation, paragraph relied upon and official source link for every authority.`),
  starter('tpl-hearing-note', 'Hearing preparation note', 'template', 'Litigation', ['Hearing', 'Court'], `HEARING NOTE

Matter: {{matter_title}}
Court and case number: {{court_case_number}}
Hearing date: {{hearing_date}}
Purpose of listing: {{listing_purpose}}

Orders already operating
{{existing_orders}}

Relief to request today
{{relief}}

Three points to open with
1. {{point_one}}
2. {{point_two}}
3. {{point_three}}

Record and page references
{{page_references}}

Likely questions and answers
{{questions}}

Instructions or settlement authority
{{instructions}}

Post-hearing actions
{{post_hearing}}`),
  starter('tpl-conference-note', 'Client conference note', 'template', 'General practice', ['Client', 'Conference'], `CLIENT CONFERENCE NOTE

Client: {{client_name}}
Date, time and attendees: {{meeting_details}}
Identity and authority verified by: {{verification}}

Instructions received
{{instructions}}

Facts stated by client
{{facts}}

Documents shown or promised
{{documents}}

Advice explained, including limitations and alternatives
{{advice}}

Decisions taken and authority given
{{decisions}}

Fees, deadlines and next contact
{{next_steps}}

Client confirmation required: {{confirmation_required}}`),
  starter('tpl-strategy-note', 'Case strategy and issue map', 'template', 'Litigation', ['Strategy', 'Issues'], `CASE STRATEGY NOTE

Matter: {{matter_title}}
Desired practical outcome: {{outcome}}

Issues requiring determination
{{issues}}

Our strongest facts and proof
{{strengths}}

Adverse facts, legal risks and missing proof
{{risks}}

Opponent's likely case
{{opponent_case}}

Interim-relief position
{{interim_relief}}

Procedural options, cost and timing
{{options}}

Settlement range and authority
{{settlement}}

Recommended plan and review date
{{recommendation}}`),
  starter('tpl-opinion', 'Legal opinion structure', 'template', 'Advisory', ['Opinion', 'Advice'], `LEGAL OPINION

Addressee and scope
{{scope}}

Questions on which opinion is requested
{{questions}}

Documents and facts considered
{{materials}}

Assumptions and matters not independently verified
{{assumptions}}

Applicable law as at {{opinion_date}}
{{law}}

Analysis
{{analysis}}

Conclusions
{{conclusions}}

Recommended action and risk controls
{{recommendations}}

Qualifications
This opinion is confined to the stated facts, documents, questions, jurisdiction and date. Update it if any of those change.`),
  starter('tpl-document-review', 'Document review memorandum', 'template', 'Due diligence', ['Documents', 'Review'], `DOCUMENT REVIEW MEMORANDUM

Transaction or dispute: {{matter_title}}
Documents reviewed: {{documents}}
Review scope and cut-off: {{scope}}

Key obligations, rights and dates
{{key_terms}}

Conditions precedent or missing approvals
{{conditions}}

Termination, default and dispute provisions
{{default_terms}}

Inconsistencies, missing pages or execution defects
{{defects}}

Stamping, registration or filing points to verify
{{formalities}}

Risk rating and recommended action
{{recommendation}}`),
  starter('tpl-settlement', 'Settlement evaluation note', 'template', 'Dispute resolution', ['Settlement', 'Risk'], `SETTLEMENT EVALUATION

Matter: {{matter_title}}
Client's non-negotiable interests: {{interests}}

Best realistic litigation outcome
{{best_outcome}}

Worst realistic litigation outcome
{{worst_outcome}}

Evidence and legal uncertainty
{{uncertainty}}

Estimated time, cost and enforcement risk
{{cost_time}}

Proposed settlement terms and alternatives
{{terms}}

Tax, confidentiality, default and withdrawal provisions
{{implementation}}

Authority obtained and expiry
{{authority}}`),
  starter('tpl-handover', 'Matter handover brief', 'template', 'Matter management', ['Handover', 'Team'], `MATTER HANDOVER BRIEF

Matter: {{matter_title}} ({{matter_number}})
Client and key contacts: {{contacts}}

Current posture and last order
{{status}}

Next hearing, limitation date and other deadlines
{{deadlines}}

Pending work and responsible persons
{{pending_work}}

Core documents and their location
{{documents}}

Strategy, settlement instructions and sensitivities
{{strategy}}

Outstanding fees or client inputs
{{outstanding}}

Handover discussion completed on: {{handover_date}}`),
];

const precedents: KnowledgeItem[] = [
  starter('pre-bail-map', 'Bail application issue map', 'precedent', 'Criminal', ['Bail', 'BNSS'], `Use this as an argument map before settling a bail application.

1. Court, FIR, offences and custody particulars.
2. Exact statutory route and court jurisdiction.
3. Prosecution allegation stated fairly and briefly.
4. Grounds: role, available record, investigation status, custody period, parity, antecedents, flight risk and witness risk.
5. Response to each prosecution concern with workable conditions.
6. Prior applications and orders disclosed accurately.
7. Precise prayer and proposed conditions.

Do not reuse section numbers or bail propositions without checking the applicable procedural law, special statute and latest binding authority.`, 'https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf'),
  starter('pre-legal-notice', 'Demand and legal notice issue map', 'precedent', 'Civil & commercial', ['Notice', 'Demand'], `Before drafting a demand notice, settle this issue map:

- Correct names, addresses, capacity and contractual relationship.
- Chronology of promise, performance, breach and communications.
- Amount calculation with invoice, payment and adjustment details.
- Contractual and statutory notice requirements.
- Clear demand, method of compliance and reasonable response date.
- Reservation of rights without exaggerated threats.
- Delivery method and proof of service.
- Limitation position recorded separately.

The final notice must match the documents and the remedy actually proposed.`),
  starter('pre-written-statement', 'Written statement issue map', 'precedent', 'Civil litigation', ['Defence', 'CPC'], `WRITTEN STATEMENT REVIEW MAP

Preliminary checks
- Service date, response deadline, court and suit identification.
- Authority, vakalatnama and supporting documents.
- Jurisdiction, limitation, maintainability and necessary parties.

Paragraph-wise response
- Admit only what can safely be admitted.
- State whether each remaining assertion is denied, not admitted or requires a specific explanation.
- Give the defendant's positive version with document references.

Defences and relief
- Set-off or counterclaim considered separately.
- Issues and legal grounds linked to pleaded facts.
- Verification, statement of truth and local rules checked.

Never use a blanket denial where procedural rules require a specific response.`, 'https://cdnbbsr.s3waas.gov.in/s3ec03a36b598abb934e4528412e5a2127/uploads/2023/09/2023091268.pdf'),
  starter('pre-rejoinder', 'Rejoinder and replication argument map', 'precedent', 'Litigation', ['Rejoinder', 'Pleadings'], `Use a rejoinder only for the procedural purpose permitted in the matter.

1. Identify new facts or defences that require a response.
2. Preserve the original case; do not quietly replace or expand it.
3. Answer material assertions in the same order as the reply.
4. Separate facts within personal knowledge from record-based statements.
5. Explain additional documents and whether leave is needed.
6. Address suppression, delay or conduct only with a factual basis.
7. End with the precise relief already maintainable.

Check the governing court rules and any order granting permission before filing.`),
  starter('pre-condonation', 'Delay-condonation application issue map', 'precedent', 'Litigation', ['Limitation', 'Delay'], `DELAY APPLICATION ISSUE MAP

- Identify the proceeding, prescribed period and exact delay calculation.
- State when the relevant order or cause became known.
- Give a date-specific explanation covering the full material period.
- Attach documents supporting illness, communication, copy application or other relied-upon facts.
- Address diligence after the stated obstacle ended.
- Explain prejudice and the merits only to the extent legally relevant.
- Include the correct supporting affidavit and prayer.

Confirm that condonation is legally available for this kind of proceeding; section 5 is not a general extension for suits.`, 'https://cdnbbsr.s3waas.gov.in/s3ec044a11654ad1e1e48352252859ff30/uploads/2023/11/2023110196.pdf'),
  starter('pre-injunction', 'Interim injunction submissions map', 'precedent', 'Civil litigation', ['Injunction', 'Interim relief'], `INTERIM INJUNCTION SUBMISSIONS

Relief sought
- State the exact act to restrain or require, parties bound and proposed duration.

Factual foundation
- Identify the existing right, threatened conduct, urgency and supporting documents.

Legal tests
- Prima facie case.
- Balance of convenience.
- Irreparable injury.
- Conduct, delay, suppression and clean hands.

Practical order
- Propose a clear, enforceable form of order.
- Address undertaking, security, notice and early return date.

Check the CPC, Specific Relief Act, governing special law, local rules and latest binding decisions.`),
  starter('pre-cheque', 'Cheque-dishonour complaint evidence map', 'precedent', 'Commercial & criminal', ['Cheque', 'NI Act'], `SECTION 138 EVIDENCE MAP

- Legally enforceable debt or liability and supporting transaction records.
- Original cheque particulars and authority/signature issues.
- Presentation date and validity.
- Bank return memo and stated reason.
- Demand notice date, contents, dispatch and delivery proof.
- Receipt or deemed-service position.
- Non-payment and complaint filing calculation.
- Correct complainant, accused, company role and territorial jurisdiction.
- Witnesses and originals to preserve.

Prepare a separate date table before drafting because the statutory sequence and time limits are strict.`, 'https://session.delhi.gov.in/session/negotiable-instruments-act'),
  starter('pre-consumer', 'Consumer complaint relief map', 'precedent', 'Consumer', ['Consumer', 'Complaint'], `CONSUMER COMPLAINT MAP

1. Complainant's consumer status and transaction.
2. Opposite parties and their respective roles.
3. Goods, service, consideration and documentary proof.
4. Defect, deficiency or unfair practice stated with dates.
5. Complaints made and responses received.
6. Jurisdiction, pecuniary basis and limitation.
7. Loss calculation and causal connection.
8. Precise relief: repair, replacement, refund, discontinuance, compensation, costs or other available order.
9. Supporting affidavit and required filing documents.

Check current rules, e-filing requirements and the competent commission before filing.`, 'https://www.indiacode.nic.in/bitstream/123456789/18555/1/consumer_protection_act_2019.pdf'),
  starter('pre-writ', 'Writ petition issue map', 'precedent', 'Public law', ['Writ', 'High Court'], `WRIT ISSUE MAP

- Petitioner, respondent authority and public-law relationship.
- Impugned action, order or inaction with certified chronology.
- Right, statutory duty and jurisdictional or procedural error relied upon.
- Alternative remedy and reason for invoking writ jurisdiction now.
- Delay, acquiescence, disputed facts and territorial jurisdiction.
- Complete disclosure of earlier proceedings and connected litigation.
- Interim relief tied to urgency and final relief.
- Annexure sequence, authentication and translation requirements.

Use the relevant High Court rules and current roster/filing directions. A writ is not a substitute for every statutory appeal.`),
  starter('pre-arbitration', 'Notice invoking arbitration issue map', 'precedent', 'Arbitration', ['Arbitration', 'Notice'], `ARBITRATION INVOCATION MAP

- Parties and contract identified exactly.
- Arbitration clause reproduced and its continuing validity checked.
- Disputes, breaches, amounts and relief summarised.
- Contractual pre-arbitration steps and notice method completed.
- Seat, venue, governing law, institution and number of arbitrators identified.
- Proposed arbitrator or appointment procedure stated.
- Limitation and date of receipt recorded.
- Reservation for quantified and presently unquantified claims used carefully.

Check the agreement, applicable institutional rules, stamping issues and current arbitration law before dispatch.`, 'https://aphc.gov.in/docs/1_20250102063311.pdf'),
];

const guides: KnowledgeItem[] = [
  starter('guide-criminal-intake', 'Criminal complaint and FIR intake workflow', 'sop', 'Criminal', ['FIR', 'Police'], `1. Record immediate safety needs and whether urgent police or medical assistance is required.
2. Capture who, what, when, where and how in the client's own words.
3. Preserve original messages, media, transaction references and device details.
4. Identify the incident date to assess BNS/IPC transition and the applicable special law.
5. Separate direct knowledge, hearsay and inference.
6. Prepare a concise chronology and persons list.
7. Record complaint submission, acknowledgement, police station and diary/FIR details.
8. Explain realistic next steps without promising registration, arrest or outcome.
9. Calendar follow-up and limitation-sensitive remedies.

Protect the identity of children and persons whose identity is restricted by law.`, 'https://www.mha.gov.in/en/commoncontent/new-criminal-laws'),
  starter('guide-bail', 'Bail matter workflow', 'sop', 'Criminal', ['Bail', 'Custody'], `INTAKE → LAW → RECORD → APPLICATION → HEARING → COMPLIANCE

Intake: obtain FIR, arrest/custody dates, remand orders, allegations, antecedents and co-accused status.
Law: confirm offence classification, special-statute restrictions, court and applicable CrPC/BNSS route.
Record: identify prosecution material, role attributed, recovery, witnesses and investigation stage.
Application: disclose prior applications; address flight, tampering and repetition risks with practical conditions.
Hearing: prepare custody calculation, parity material, page references and proposed order.
After order: explain bond, surety, reporting, travel and contact conditions; calendar compliance.

Urgent liberty matters require date-specific review by the responsible lawyer.`),
  starter('guide-civil-suit', 'Civil suit commencement workflow', 'sop', 'Civil litigation', ['Civil suit', 'CPC'], `1. Define the client's enforceable right and desired relief.
2. Build a chronology and document index.
3. Identify cause of action, parties, territorial/pecuniary jurisdiction and limitation.
4. Check notice, mediation or pre-institution requirements.
5. Evaluate interim relief and preservation of property or evidence.
6. Draft material facts, legal grounds and prayers consistently.
7. Calculate valuation and court fee; check stamping and registration issues.
8. Prepare list of documents, statements, affidavits and local-rule forms.
9. Complete pre-filing review for names, dates, annexures, pagination and authority.
10. Preserve filing proof, defects and service steps.`, 'https://cdnbbsr.s3waas.gov.in/s3ec03a36b598abb934e4528412e5a2127/uploads/2023/09/2023091268.pdf'),
  starter('guide-cheque', 'Cheque dishonour workflow', 'sop', 'Commercial & criminal', ['Cheque', 'Section 138'], `1. Obtain cheque, bank memo, underlying agreement/invoice and payment ledger.
2. Create a statutory date table immediately.
3. Confirm the cheque was for a legally enforceable debt or liability.
4. Verify drawer, account, company role and signature issues.
5. Prepare and dispatch a compliant demand notice using provable delivery channels.
6. Monitor receipt/deemed service and payment period.
7. Calculate complaint limitation and jurisdiction from verified facts.
8. Assemble originals, affidavit, authority and filing requirements.
9. Consider parallel civil recovery, settlement and insolvency implications separately.

Do not rely on a generic timeline; calculate every deadline from the Act and current case law.`),
  starter('guide-consumer', 'Consumer dispute workflow', 'sop', 'Consumer', ['Consumer', 'Refund'], `1. Confirm consumer status, transaction, consideration and parties.
2. Collect invoice, warranty, product/service description, communications and photographs.
3. State the defect, deficiency or unfair practice and the remedy already requested.
4. Send an appropriate complaint/demand and preserve responses.
5. Check limitation, territorial and pecuniary jurisdiction and e-filing requirements.
6. Quantify refund, repair cost and other claimed loss with proof.
7. Draft concise facts, relief and supporting affidavit.
8. Track admission, notice, reply, evidence, hearing and compliance.

Contract, RERA, sectoral regulator or other remedies may also require assessment.`, 'https://www.indiacode.nic.in/bitstream/123456789/18555/1/consumer_protection_act_2019.pdf'),
  starter('guide-rera', 'Homebuyer and RERA dispute workflow', 'sop', 'Real estate', ['RERA', 'Homebuyer'], `1. Obtain allotment/application, agreement, payment receipts and promised possession date.
2. Check project and agent registration on the relevant State RERA portal.
3. Compare sanctioned disclosures, agreement milestones and actual status.
4. Record delay, demand changes, correspondence and possession offers.
5. Identify desired outcome: possession, interest, refund, rectification or compensation.
6. Check State rules, authority jurisdiction, limitation and parallel proceedings.
7. Prepare calculation with dates and supporting documents.
8. File in the prescribed format and track service, reply, hearing and enforcement.

Project coverage, State rules and the chosen remedy materially affect the route.`, 'https://www.indiacode.nic.in/bitstream/123456789/2154/5/A2016-31.pdf'),
  starter('guide-family', 'Matrimonial matter intake workflow', 'sop', 'Family', ['Marriage', 'Family'], `1. Identify marriage law, date, place, ceremony and registration.
2. Record separation, children, residence and any immediate safety concern.
3. Build a neutral chronology, separating allegations from available proof.
4. Collect marriage, identity, residence, income, asset and prior-order records.
5. Map possible relief concerning status, protection, residence, maintenance, custody and property.
6. Check jurisdiction, mandatory periods, mediation and urgent interim relief.
7. Protect sensitive data and avoid unsafe evidence collection.
8. Explain confidentiality, realistic outcomes and the impact on children.

Use a safety plan and specialised support where violence or coercive control is alleged.`, 'https://www.spniwcd.wcd.gov.in/uploads/pdf/1714714662.pdf'),
  starter('guide-arbitration', 'Arbitration matter workflow', 'sop', 'Arbitration', ['Arbitration', 'Commercial'], `1. Locate the signed arbitration agreement and all incorporated documents.
2. Identify disputes, claims, counterclaims, contractual steps and limitation dates.
3. Determine seat, venue, governing law, institution and appointment method.
4. Preserve notices, evidence and proof of service.
5. Consider urgent court or emergency relief and asset preservation.
6. Invoke arbitration in accordance with the clause and governing law.
7. Calendar appointment, pleadings, evidence, hearing and award deadlines.
8. Maintain a claim calculation and costs record.
9. On award, calculate challenge/enforcement dates immediately.

Seat and limitation decisions should be reviewed before the first notice is sent.`, 'https://aphc.gov.in/docs/1_20250102063311.pdf'),
  starter('guide-company', 'Private company annual compliance workflow', 'sop', 'Corporate', ['Company', 'Compliance'], `Use this as an internal planning guide; confirm current MCA forms and deadlines.

1. Maintain statutory registers, minutes and disclosures.
2. Plan board and member approvals against the company's constitution and law.
3. Track director KYC, interests, related-party matters and changes.
4. Coordinate accounts, audit, financial statements and annual return.
5. Record event-based filings for office, capital, directors, charges and key agreements.
6. Monitor beneficial ownership and other applicable disclosures.
7. Preserve challans, acknowledgements and signed records.
8. Escalate defaults early and document corrective steps.

Applicability varies by company type, thresholds, exemptions and notifications.`, 'https://nclt.gov.in/sites/default/files/basicpage/the_companies_act_2013.pdf'),
  starter('guide-legal-aid', 'Legal aid and Lok Adalat referral workflow', 'sop', 'Access to justice', ['Legal aid', 'Lok Adalat'], `1. Identify the client's immediate proceeding, deadline and assistance needed.
2. Check statutory eligibility categories and current local income limits.
3. Collect identity, case papers and the documents requested by the authority.
4. Locate the Taluk, District, High Court or State Legal Services Authority concerned.
5. Submit the application and retain acknowledgement/contact details.
6. For Lok Adalat, confirm the dispute is legally capable of settlement and that consent is informed.
7. Explain that settlement terms become binding and should be read before signature.
8. Continue protecting limitation and court deadlines until assistance is confirmed.`, 'https://nalsa.gov.in/the-legal-services-authorities-act-1987/'),
];

const checklists: KnowledgeItem[] = [
  starter('check-intake', 'New matter intake checklist', 'checklist', 'Matter management', ['Intake', 'Conflict'], `- Record client name, contact details, preferred language and authorised representatives
- Complete identity, authority and conflict checks
- Record opposing parties, related entities and connected matters
- Capture the client's objective and immediate urgency
- Obtain a concise chronology and key documents
- Identify hearing dates, notices and possible limitation dates
- Define scope, exclusions, responsible lawyer and communication method
- Explain fees, expenses and document-retention expectations
- Issue and record engagement documentation
- Create the matter, permissions, tasks and first review date`),
  starter('check-limitation', 'Limitation and deadline checklist', 'checklist', 'Litigation', ['Limitation', 'Deadlines'], `- Identify the exact cause of action, proceeding and relief
- Record the first possible accrual date and all competing dates
- Find the applicable schedule entry and any special-statute period
- Check exclusion, acknowledgment, fraud, disability and continuing-cause provisions
- Confirm whether condonation is legally available
- Record certified-copy application and delivery dates where relevant
- Check court holidays and filing rules
- Calculate using a second-person review
- Calendar an internal deadline before the legal deadline
- Preserve the calculation and source provisions in the matter`),
  starter('check-filing', 'Court filing quality checklist', 'checklist', 'Litigation', ['Filing', 'Court'], `- Confirm court, jurisdiction, case type and current filing rules
- Verify party names, descriptions, addresses and authority
- Check limitation, valuation, court fee and process fee
- Confirm pleadings, prayers and interim relief are consistent
- Verify paragraph numbering, dates, amounts and cross-references
- Complete verification, affidavit and statement of truth where required
- Index and paginate legible annexures in the cited order
- Check translations, redaction and confidential filing requirements
- Sign every required page and attach vakalatnama or authority
- Retain filing acknowledgement, diary number and defect notes`),
  starter('check-evidence', 'Evidence collection checklist', 'checklist', 'Litigation', ['Evidence', 'Documents'], `- List each fact that must be proved and who bears the burden
- Identify the witness or record capable of proving each fact
- Preserve originals and record where each item came from
- Create a dated document index and chain-of-custody note
- Separate privileged, confidential and personal data
- Record authenticity, execution and handwriting/signature issues
- Collect certified copies where legally required
- Check stamping, registration and admissibility objections
- Map every relied-upon document to a pleading and witness
- Record missing evidence and lawful steps to obtain it`),
  starter('check-digital', 'Electronic evidence checklist', 'checklist', 'Technology & evidence', ['Electronic evidence', 'BSA'], `- Preserve the original device, account or system where reasonably possible
- Export the complete conversation or record with metadata
- Record date, time zone, account identifiers and collection method
- Avoid editing, annotating or repeatedly forwarding the only copy
- Calculate and preserve file hashes where appropriate
- Identify the person or system responsible for producing the record
- Assess the applicable certificate and foundational evidence requirements
- Preserve server, bank, telecom or platform requests promptly
- Prepare a readable court copy without losing the original
- Protect privileged, confidential and third-party personal data`),
  starter('check-hearing', 'Hearing readiness checklist', 'checklist', 'Litigation', ['Hearing', 'Advocacy'], `- Confirm date, court, item number, purpose and mode of hearing
- Read the latest order and note every direction
- Check compliance, service and pending defects
- Prepare a one-page chronology and issue list
- Mark the relief requested and exact supporting page references
- Update authorities and verify current status
- Anticipate the opponent's strongest point and the court's likely questions
- Confirm client instructions and settlement authority
- Carry accessible copies of the record and proposed order
- Record the result, next date and tasks immediately after hearing`),
  starter('check-due-diligence', 'Legal due diligence checklist', 'checklist', 'Corporate', ['Due diligence', 'Transaction'], `- Confirm scope, materiality, period and data-room cut-off
- Review incorporation, authority, ownership and constitutional records
- Check material contracts, change-of-control and termination rights
- Review licences, regulatory approvals and compliance history
- Check litigation, notices, investigations and contingent liabilities
- Review property, leases, charges and security interests
- Review employment, benefits and key-person arrangements
- Check intellectual property ownership and data/privacy obligations
- Reconcile missing, expired, unsigned or inconsistent documents
- Report findings by risk, evidence, consequence and recommended action`),
  starter('check-appeal', 'Appeal preparation checklist', 'checklist', 'Litigation', ['Appeal', 'Limitation'], `- Obtain the complete impugned judgment/order and operative directions
- Record pronouncement, knowledge, copy-application and receipt dates
- Confirm appeal/revision route, forum and maintainability
- Calculate limitation and assess stay urgency
- Identify reviewable errors with exact record references
- Separate factual challenge, legal error and procedural unfairness
- Check preservation of objections and additional-evidence restrictions
- Draft concise grounds without evidence or argument not supported by record
- Prepare stay application, deposit/security position and proposed order
- Verify certified copies, paper-book and service requirements`),
  starter('check-settlement', 'Settlement documentation checklist', 'checklist', 'Dispute resolution', ['Settlement', 'Agreement'], `- Verify parties, authority and informed consent
- Define every payment, transfer, action and deadline precisely
- State tax, fee and expense responsibility
- Address withdrawal, disposal and release of proceedings
- Define confidentiality and legally required disclosures
- Deal with admissions, no-admission language and future claims carefully
- Include representations necessary for implementation
- Set consequences, cure and enforcement for default
- Address return, destruction or retention of documents and property
- Record signatures, witnesses, stamping, filing and completion evidence`),
  starter('check-closing', 'Matter closing and archive checklist', 'checklist', 'Matter management', ['Closing', 'Archive'], `- Confirm final order, settlement or completed advice with the responsible lawyer
- Explain outcome, obligations and future deadlines to the client
- Calendar appeal, compliance, renewal or enforcement dates
- Complete final billing and trust/client-money reconciliation
- Return originals against acknowledgement where appropriate
- Save final signed documents, orders and key correspondence
- Record reusable learning only after removing confidential identifiers
- Apply retention, legal-hold and secure-destruction rules
- Restrict or close access for external collaborators
- Send closure communication and record the archive location`),
];

const notes: KnowledgeItem[] = [
  starter('note-bns-ipc', 'IPC to BNS transition research note', 'note', 'Criminal', ['IPC', 'BNS', 'Transition'], `Research position
The Bharatiya Nyaya Sanhita, 2023 replaced the Indian Penal Code, subject to statutory savings. The applicable offence law requires a date-specific analysis.

Questions to answer
1. When did the alleged act or omission occur?
2. Was it a continuing course of conduct?
3. What does the BNS repeal-and-savings provision preserve?
4. Are the old and new offence ingredients actually equivalent?
5. Is a special or local penal statute more specific?

Working rule
Do not mechanically replace an IPC section number with a BNS number. Compare ingredients, explanations, illustrations, punishment, territorial reach and the savings clause. Record the conclusion in the matter with the official texts and commencement notification.`, 'https://www.mha.gov.in/en/commoncontent/new-criminal-laws'),
  starter('note-bnss-crpc', 'CrPC to BNSS transition research note', 'note', 'Criminal procedure', ['CrPC', 'BNSS', 'Transition'], `Research position
BNSS commenced as the general criminal procedure law on 1 July 2024, while its savings provision preserves specified pending proceedings under CrPC.

Checklist for the research note
- Identify the procedural step in dispute.
- Record whether an appeal, application, trial, inquiry or investigation was pending at commencement.
- Read BNSS section 531 and any applicable special-law provision.
- Check whether later proceedings are part of a saved proceeding.
- Verify the current court practice and binding authority.

The incident date alone does not determine every procedural question. State the procedural history and the reason for choosing CrPC or BNSS.`, 'https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf'),
  starter('note-bsa-evidence', 'Evidence Act to BSA transition note', 'note', 'Evidence', ['Evidence Act', 'BSA', 'Transition'], `The Bharatiya Sakshya Adhiniyam, 2023 replaced the Indian Evidence Act subject to its savings provision.

For each matter record:
- proceeding type and commencement status on 1 July 2024;
- the particular evidentiary question;
- old and new provisions compared by substance;
- the savings analysis;
- procedural law affecting proof or certificates;
- binding decisions that remain relevant and why.

Electronic-record terminology and proof requirements require close reading. Avoid changing statutory references in an older pleading or judgment without explaining the transition.`, 'https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf'),
  starter('note-electronic', 'Electronic records proof research note', 'note', 'Technology & evidence', ['Electronic evidence', 'BSA'], `Issue framework
1. What electronic record is relied upon?
2. Is the original device/system available, or is a computer output being tendered?
3. Who can explain creation, storage, retrieval and integrity?
4. What statutory certificate or foundational proof applies to this proceeding?
5. Is metadata, a provider record, hash or expert evidence needed?
6. Are authenticity, authorship, completeness or hearsay disputed separately?

Practical point
A screenshot may be useful information but does not by itself answer every admissibility and weight question. Preserve the original source and document the collection method before preparing court copies.`, 'https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf'),
  starter('note-injunction', 'Interim injunction research note', 'note', 'Civil litigation', ['Injunction', 'CPC'], `Core research headings
- Source of the asserted legal right.
- Threatened or continuing breach.
- Prima facie case.
- Balance of convenience.
- Irreparable injury.
- Delay, acquiescence, suppression and conduct.
- Mandatory versus prohibitory relief.
- Ex parte requirements and prompt return hearing.
- Undertaking, security and enforceability of proposed order.

Research the governing special statute and current binding decisions in addition to the CPC and Specific Relief Act. Tie every proposition to facts and to the exact interim order requested.`),
  starter('note-limitation', 'Limitation calculation research note', 'note', 'Litigation', ['Limitation', 'Deadlines'], `Method
1. Characterise the proceeding and relief accurately.
2. Identify the applicable schedule article or special statute.
3. Determine the legally relevant accrual/knowledge/order date.
4. Test alternate dates advanced by each side.
5. Apply exclusions, acknowledgment, fraud, disability or continuing wrong only where facts and law support them.
6. Check whether condonation is available.
7. Show the calculation transparently, including copy time and holidays.

Record a conservative internal deadline. Limitation conclusions should cite the provision and verified facts, rather than a general statement such as “three years.”`, 'https://cdnbbsr.s3waas.gov.in/s3ec044a11654ad1e1e48352252859ff30/uploads/2023/11/2023110196.pdf'),
  starter('note-jurisdiction', 'Civil jurisdiction research note', 'note', 'Civil litigation', ['Jurisdiction', 'CPC'], `Analyse jurisdiction under separate headings:

Subject matter: Is jurisdiction conferred or excluded by a special statute?
Territorial: Where did the relevant cause of action arise and where do defendants reside/carry on business?
Pecuniary: How is the suit or relief valued under applicable law?
Forum clause: Is it valid and does the chosen court otherwise possess jurisdiction?
Arbitration: Does an arbitration agreement affect the court route?
Procedural stage: When and how must an objection be raised?

Use facts from the pleading and documents. Do not treat party convenience as jurisdiction. Check State amendments, commercial court legislation and local rules.`, 'https://cdnbbsr.s3waas.gov.in/s3ec03a36b598abb934e4528412e5a2127/uploads/2023/09/2023091268.pdf'),
  starter('note-breach-cheating', 'Contract breach versus criminal cheating note', 'note', 'Civil & criminal', ['Contract', 'Cheating'], `Research question
Does the material support a civil breach, the criminal offence of cheating, or potentially both?

Facts to test
- Representation or promise alleged.
- State of mind when the representation induced action.
- Property delivered or harmful act/omission caused.
- Subsequent non-performance and explanations.
- False documents, concealment or contemporaneous communications.
- Contractual allocation of risk and dispute mechanism.

Non-performance alone does not establish the required dishonest intention at inception. Equally, a contractual relationship does not automatically bar criminal liability where every offence ingredient is supported. Analyse the statutory ingredients and evidence without using the criminal process merely as recovery pressure.`, 'https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf'),
  starter('note-precedent', 'Judgment and precedent research method', 'note', 'Research', ['Judgments', 'Precedent'], `For every judgment relied upon, record:

1. Court, bench strength, date and neutral/official citation.
2. Procedural posture and material facts.
3. Exact question decided.
4. Holding with paragraph references.
5. Ratio distinguished from observations, concessions and factual findings.
6. Earlier binding authority considered.
7. Later history: appeal, review, overruling, distinguishing or statutory change.
8. Jurisdictional and bench-strength hierarchy.
9. How the proposition applies to the present facts.
10. Official or authoritative source link.

Read the complete judgment. A headnote or search snippet is a research lead, not the final authority.`),
  starter('note-source-check', 'Legal source verification protocol', 'note', 'Research', ['Sources', 'Quality control'], `SOURCE ORDER
1. Current official statutory text, rules and Gazette notifications.
2. Official court judgment/order or authenticated copy.
3. Binding later authority and amendment history.
4. Reliable commentary for discovery and context.

Before using a proposition
- Open the source and read the surrounding provision or paragraphs.
- Confirm court, bench, date, parties and citation.
- Check amendments, commencement, repeal and savings.
- Check later treatment and pending/final status where relevant.
- Record the retrieval date and paragraph/page relied upon.
- Label summaries as summaries and quotations as exact quotations.

Do not cite an AI response, news report or search-result snippet as legal authority.`),
];

export const FIRM_LIBRARY_STARTERS: KnowledgeItem[] = [
  ...templates,
  ...precedents,
  ...guides,
  ...checklists,
  ...notes,
];

export function filteredFirmStarters(
  category: KnowledgeCategory | '',
  query: string,
  practiceArea: string,
): KnowledgeItem[] {
  const q = query.trim().toLowerCase();
  const area = practiceArea.trim().toLowerCase();
  return FIRM_LIBRARY_STARTERS.filter((item) =>
    (!category || item.category === category)
    && (!area || (item.practice_area ?? '').toLowerCase().includes(area))
    && (!q || `${item.title} ${item.body} ${item.practice_area} ${item.tags.join(' ')}`.toLowerCase().includes(q)),
  );
}

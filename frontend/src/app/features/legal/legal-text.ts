/**
 * Source text for the public /privacy and /terms pages. Generated from
 * docs/PRIVACY_NOTICE.md and docs/TERMS.md — edit those files and re-copy;
 * bump CURRENT_TERMS_VERSION / CURRENT_PRIVACY_NOTICE_VERSION on the backend
 * when the substance changes.
 */
export const LEGAL_VERSION = '2026-09-27';

export const PRIVACY_NOTICE_MD = `# VidhiSangh Privacy Notice

**Version 2026-09-27 · Effective 27 September 2026**

This notice is given under section 5 of the Digital Personal Data Protection Act, 2023 ("DPDP Act"). It explains what personal data VidhiSangh collects, why, for how long, who else touches it, and how you exercise your rights. It is written in plain English; a Hindi translation is available on request from the Grievance Officer (s.5(3)).

VidhiSangh ("we") is operated by VidhiSangh, India. Contact details for privacy matters are in section 10.

---

## 1. Who we are to you

VidhiSangh is a practice-management and professional-network platform for advocates and law firms in India. Depending on who you are, we act in one of two capacities:

| You are | We are | What that means |
|---|---|---|
| **A user** — an advocate, staff member, student or other person with an account | **Data Fiduciary** | We decide why and how your account, profile and network data are processed. This notice is our notice to you. |
| **A client, party, lead or other person whose data a law firm stores in VidhiSangh** | **Data Processor** for that firm | The **firm** is the Data Fiduciary. It decides what to collect and why; we process the data on its written instructions (our Terms, Schedule A). The firm must give you its own notice; the version shown on the KYC form is the firm's notice rendered by us. Section 9 below explains what we do as processor. |

## 2. Personal data we collect (users)

| Category | Items | Source |
|---|---|---|
| Account | Name, work e-mail, password (stored as an Argon2id hash), phone (optional), avatar | You, at sign-up |
| Organisation | Firm name, slug, plan, contact e-mail | You / your administrator |
| Professional profile | Headline, bio, bar enrolment number and council, years of experience, practice areas, courts, languages, education, publications, city, office address, website, LinkedIn, consultation fee | You |
| Network activity | Posts, comments, reactions, connections, follows, group memberships, messages you send, endorsements and recommendations you give | You |
| Security | MFA secret (encrypted), backup-code hashes, passkey public keys, session records (device label, IP address, browser user-agent, timestamps), failed-login counters, security audit events | Generated as you use the service |
| Sign-in via a third party | E-mail, name and provider subject id from Google, Microsoft or LinkedIn — only if you choose that option | The provider you pick |
| Payments | Name, e-mail, amount, Razorpay payment/order ids. **We never see or store card or bank details.** | Razorpay |
| Notifications | In-app notifications and a delivery log (channel, status; addresses are masked) | Generated |
| Preferences | Theme, accent colour, notification channels | You (theme is kept in your browser only) |
| Terms acceptance | Version of the Terms and this Notice you accepted, and when | You, at sign-up |

We do **not** collect biometric data, location, contacts or anything from your device beyond what your browser sends with a normal web request.

## 3. Why we process it (purposes) and the lawful basis

| Purpose | Basis under the DPDP Act |
|---|---|
| Creating and securing your account; signing you in; MFA; detecting attacks | Consent given at sign-up (s.6); and legitimate use — it is necessary to provide what you asked for (s.7(a)) |
| Running the practice-management features your firm uses | Consent / s.7(a) |
| Publishing your professional profile in the cross-tenant directory and network | Consent. **You can opt out** in Settings → Privacy & data → "Directory listing" at any time; your profile then disappears from discovery |
| Sending **push notifications** to the mobile app | Consent, given through your phone's notification permission. We store the app's Firebase device token (Google Firebase Cloud Messaging delivers the message); it is deleted when you sign out or Firebase reports it invalid. Switch off in Settings → Notifications or in your phone's settings |
| Publishing a **public profile page** at vidhisangh.com/in/your-name, open to anyone and to search engines | Consent, given separately and only if you switch it on in Settings → Privacy & data → "Public profile page". It shows your name, photo, headline and the profile sections you set to "Everyone"; never your contact details. Withdraw by switching it off; the page is removed at once (search engines may take a few days to drop it) |
| Sending notifications you turned on (e-mail, Slack) | Consent, per channel, in Settings → Notifications |
| Billing your organisation | Performance of the contract; legal obligation (GST) |
| Security logging and the audit trail | Legal obligation and legitimate use (s.7) — this is why audit entries are kept even after an account is erased |
| Responding to your rights requests and grievances | Legal obligation (s.11–13) |

We do not sell personal data, profile you for advertising, or use tracking pixels.

## 4. How long we keep it (retention)

| Data | Retention |
|---|---|
| Account and profile | Until you delete your account; then anonymised immediately |
| Sessions (refresh tokens) | Deleted 30 days after expiry or revocation; the IP address and user-agent are removed as soon as the session is revoked |
| Sign-in state (OAuth, passkey challenges) | Deleted within one day of expiry |
| Used MFA backup codes | Deleted on the next nightly run |
| In-app notifications | 365 days |
| Notification delivery log | 90 days |
| Deleted documents and drafts (soft-deleted) | 30 days in the recycle state, then the file bytes and records are destroyed |
| Security audit log | Retained for the life of the organisation (legal obligation) |
| Whole organisation after cancellation | Disabled at once; everything erased 30 days later (grace period for the owner to change their mind or export) |
| Client, matter and invoice records held for a firm | As instructed by the firm; by default 8 years after a matter closes (Limitation Act, 1963 and Bar Council record-keeping practice), then erasable |

The retention job runs nightly (\`infra/jobs/vidhisangh-retention.timer\`). Periods are configurable by the operator and the current values are published at \`/api/v1/privacy/notice\`.

## 5. Your rights (s.11–s.14) and how to use them

| Right | How |
|---|---|
| **Access** (s.11) — a copy of everything we hold about you | Settings → Privacy & data → *Download my data* (JSON), or \`GET /api/v1/privacy/me/export\` |
| **Correction and completion** (s.12) | Edit your profile and account directly; ask the Grievance Officer for anything you cannot edit |
| **Erasure** (s.12) | Settings → Privacy & data → *Delete my account* (password required). Your account is anonymised at once and your sessions revoked. If you are the only administrator of your firm, transfer that role first or delete the organisation instead. Audit entries naming you are retained under s.17(1)(a) |
| **Withdraw consent** (s.6(4)) | Untick a notification channel, opt out of the directory, switch off your public profile page, or delete the account. Withdrawal is as easy as giving consent and does not affect processing done before it |
| **Grievance redressal** (s.13) | Write to the Grievance Officer (section 10). We acknowledge within 7 days and respond within 30 days |
| **Nominate** (s.14) | E-mail the Grievance Officer with the nominee's details; we will record them against your account |
| **Complain to the Board** | If you are not satisfied with our response, you may complain to the **Data Protection Board of India** (https://www.dpb.gov.in/) |

You have duties too (s.15): do not impersonate anyone, do not suppress material information when giving data for a legal purpose, and do not raise false or frivolous grievances.

## 6. Where your data is and who else processes it (s.16 transfers)

All production data is hosted on servers in **India (ap-south-1 / Mumbai region)**. We use the following sub-processors; each receives only what its purpose needs:

| Sub-processor | Purpose | Data shared |
|---|---|---|
| SMTP e-mail provider (the operator's configured provider) | Transactional e-mail — KYC links, invitations, notifications | Name, e-mail address, message text |
| Slack (your firm's own webhook, configured by your administrator) | Firm notifications | Notification text only; goes to your firm's workspace |
| Razorpay | Subscription and invoice payments | Name, e-mail, amount |
| Google / Microsoft / LinkedIn | Single sign-on, only when you choose it | E-mail, name, subject identifier |
| Google Firebase Cloud Messaging | Push notifications to the mobile app, only if you allow them | Device token, notification text |
| Meta Platforms (WhatsApp Business) | WhatsApp sign-in codes, and hearing reminders if you turn them on | Mobile number, the code or the list of next-day hearings |
| Brevo (Sendinblue SAS) | Invitation e-mails to people not yet on VidhiSangh, from public professional listings | E-mail address, name, the listing it came from |
| Hosting provider (India) | Servers, database, document storage | All platform data, encrypted at rest |

Firms may also configure outbound webhooks to their own systems; those are the firm's processors, not ours. We will update this table before adding a sub-processor.

## 7. Children (s.9)

VidhiSangh accounts are for legal professionals and students aged 18 or over. We do not knowingly create accounts for children, we do no behavioural tracking or targeted advertising of anyone, and we run no processing likely to harm a child.

A law firm may need to record a **minor as a client** (for example in a guardianship or custody matter). For that case the platform provides a *minor* flag and guardian fields; the firm must record the parent's or lawful guardian's **verifiable consent** as a consent-ledger entry before a KYC form can be sent to that client. The firm is the Data Fiduciary for that decision.

## 8. Cookies and local storage

We set **no cookies** and use **no analytics or advertising trackers**. Your browser's local storage holds your session tokens, your theme choice and unsent drafts so the app works between page loads; nothing in it is read by anyone else. Clearing site data signs you out.

## 9. What we do as a Data Processor for law firms

When a firm records a client, opposing party, lead or witness in VidhiSangh:

- The **firm** decides the purpose and lawful basis and must give that person its own notice. The KYC form carries the firm's notice text and the version the person saw is stored with their declaration.
- Client identity data (PAN, GSTIN, TAN, CIN, Udyam, date of birth, father's or spouse's name, phone numbers) is **encrypted at rest**; exact-match search uses keyed blind indexes so plaintext is never searched.
- Consent to be contacted is recorded per channel as an **append-only ledger**; a withdrawal never deletes the original grant, and the platform refuses to send a client-facing message on a channel without a current grant (except messages the engagement itself requires, which are sent on the basis of the contract and marked as such).
- We provide the firm with the tools to honour rights requests: per-client export, correction, erasure (with a legal-hold check against open or recently closed matters), and a register of requests and grievances.
- Firm staff can see only their own firm's data (database row-level security), and the platform operator's staff do not read client data except to resolve a support request the firm raises, under confidentiality.
- The firm can export everything and delete the whole organisation at any time (Settings → Privacy & data). Erasure is completed 30 days after cancellation.

## 10. Grievance Officer (s.8(9), s.13)

| | |
|---|---|
| Name | Salil Shaida |
| E-mail | grievance@vidhisangh.com |
| Postal address | *set via \`VS_GRIEVANCE_OFFICER_ADDRESS\`* |

The live values are shown on the [/privacy](https://vidhisangh.com/privacy) page and on every KYC form, and are returned by \`GET /api/v1/privacy/notice\`. If you have a grievance about a **firm's** handling of your data, contact that firm first; its data-protection contact is shown on its KYC form.

## 11. Security in brief

Argon2id password hashing, short-lived access tokens with rotating refresh tokens, optional MFA and passkeys, PostgreSQL row-level security for tenant isolation, field-level encryption for client identity data, TLS in transit, security-event audit trail. The full controls matrix is in \`docs/SECURITY.md\`.

## 12. Changes to this notice

We will publish a new version here with a new date, and existing users will be asked to review it on their next sign-in. Material reductions in your rights will never apply retroactively.

## 13. Breach notification

If a personal-data breach affects you, we will notify the Data Protection Board and you as required by s.8(6) and the rules made under it, describing what happened, what data was involved and what we are doing about it.
`;

export const TERMS_MD = `# VidhiSangh Terms of Service

**Version 2026-09-27 · Effective 27 September 2026**

These Terms govern your use of VidhiSangh (the "Service"), operated by VidhiSangh, India ("we", "us"). By creating an account you accept these Terms and the [Privacy Notice](PRIVACY_NOTICE.md) on behalf of yourself and, if you create an organisation, on behalf of that organisation (the "Firm"). The version you accepted and the time of acceptance are recorded against your account.

## 1. The Service

VidhiSangh provides practice management (matters, clients, documents, drafting, billing), legal research over public judgments, and a professional network for advocates, law firms and law students in India. Features vary by plan. We may improve, add or retire features with reasonable notice.

## 2. Eligibility and accounts

- You must be at least 18 and, where you hold yourself out as an advocate, enrolled with a State Bar Council.
- Keep your credentials confidential. Enable multi-factor authentication for accounts that hold client data. You are responsible for activity under your account until you tell us it is compromised.
- One e-mail address identifies one account on the platform.

## 3. Organisations, roles and administrators

The person who creates a Firm is its first **administrator** (\`org_admin\`). Administrators add users, assign roles and permissions, and may export or delete the Firm. The Firm is responsible for its users' compliance with these Terms. A Firm must keep at least one active administrator; an administrator who wants to leave must first make another user an administrator or delete the Firm.

## 4. Acceptable use

You will not: use the Service to break the law or the Bar Council of India Rules (including the restrictions on advertising and solicitation); upload malware; attempt to access another Firm's data; scrape the network or the judgment corpus for bulk redistribution; impersonate anyone; post content that is defamatory, harassing or infringes rights; or interfere with the Service's security controls.

## 5. Your content and client data

- **You own** what you and your Firm put into the Service. You grant us a licence to host, process, back up and display it only as needed to run the Service for you.
- **Client and matter data is the Firm's.** We are a Data Processor for it (Schedule A). We do not use it to train models, for marketing, or for any purpose of our own.
- **Professional-network content** (posts, comments, profile) is visible to other users as you choose (public / connections) and across Firms. You can opt out of the directory at any time. If you switch on a public profile page, the parts of your profile you set to "Everyone" are also published on the open web at vidhisangh.com/in/your-name; you can switch it off at any time.
- **Public judgments** in the research library are court records reproduced for legal research. If you believe a record is inaccurate or should be redacted under a court order, write to the Grievance Officer.

## 6. Confidentiality and professional obligations

The Service is a tool; it does not replace your professional judgment. Advocate–client privilege, confidentiality duties and court rules remain yours to honour. Share portal links and KYC forms only with the person they are meant for.

## 7. Fees and payment

Paid plans are billed in advance through Razorpay in Indian Rupees, plus GST. Fees are non-refundable except as required by law or stated in a plan. We may suspend a Firm for non-payment after 14 days' notice; data is retained during suspension and is subject to Section 10 on cancellation.

## 8. Availability, support and changes

We aim for high availability but do not guarantee uninterrupted service. Planned maintenance is announced in the app. Support is by e-mail. We may change these Terms; material changes are notified 30 days in advance and you will be asked to accept the new version at sign-in. Continuing to use the Service after that date is acceptance.

## 9. Security

We apply the controls described in \`docs/SECURITY.md\` (encryption at rest for client identity data, row-level tenant isolation, hashed credentials, audit trail, retention purges). You must report suspected security incidents to security@vidhisangh.com without undue delay.

## 10. Term, export and deletion

- **Your account**: you may delete it at any time from Settings → Privacy & data. It is anonymised immediately; see the Privacy Notice for what is retained and why.
- **The Firm**: an administrator may export everything (a zip of every table) and delete the Firm. Deletion disables every user at once and permanently erases all Firm data 30 days later. During those 30 days the Firm may ask us in writing to reinstate it.
- **By us**: we may terminate for material breach of Section 4 or non-payment. We will give the Firm 30 days to export its data unless the law or the safety of others prevents it.

## 11. Disclaimers and liability

The Service is provided "as is". We do not give legal advice and are not responsible for the outcome of any matter. To the extent permitted by law, our total liability to you for any claim in a year is limited to the fees the Firm paid us in the preceding twelve months. Nothing limits liability for fraud, death or personal injury, or breach of Schedule A caused by our gross negligence.

## 12. Governing law and disputes

These Terms are governed by the laws of India. Courts at New Delhi have exclusive jurisdiction, subject to any mandatory forum for consumer disputes. Data-protection complaints may also be made to the Data Protection Board of India.

## 13. Notices and contact

Legal notices: legal@vidhisangh.com. Privacy and grievances: the Grievance Officer named in the Privacy Notice and at \`/privacy\`. Security: security@vidhisangh.com.

---

## Schedule A — Data Processing Terms (Firm as Data Fiduciary, VidhiSangh as Data Processor)

1. **Scope.** This Schedule applies to personal data of clients, parties, leads, witnesses and other persons that the Firm stores in the Service ("Firm Data"). The Firm is the Data Fiduciary and VidhiSangh the Data Processor under the DPDP Act, 2023.
2. **Instructions.** We process Firm Data only to provide the Service as configured by the Firm and as documented in these Terms. The Firm's use of a feature (for example sending a KYC form) is its instruction to perform that processing.
3. **The Firm's obligations.** The Firm is responsible for having a lawful basis, for giving notice under s.5 to the persons concerned, for recording consent where consent is the basis (the Service supplies an append-only consent ledger for this), for recording verifiable guardian consent before processing a child's data, and for responding to rights requests. The Service provides export, correction, erasure (with legal-hold safeguards) and a request register to help it do so.
4. **Security (s.8(5)).** We maintain the technical and organisational measures in \`docs/SECURITY.md\`, including encryption of client identity data at rest, row-level tenant isolation, hashed tokens and credentials, TLS, audit logging and scheduled retention purges.
5. **Confidentiality.** Our personnel access Firm Data only to resolve a support request the Firm raises, under written confidentiality obligations, and every such access is logged.
6. **Sub-processors.** Listed in section 6 of the Privacy Notice. We will update the list before engaging a new sub-processor; the Firm may object within 30 days and terminate if we cannot resolve the objection.
7. **Location.** Firm Data is stored and processed in India.
8. **Breach.** We notify the Firm without undue delay, and in any case within 72 hours of confirming a personal-data breach affecting Firm Data, with the information the Firm needs to meet its own s.8(6) duties.
9. **Assistance.** We help the Firm respond to access, correction and erasure requests through the Service's export and erasure functions and, where needed, manual assistance at cost.
10. **Return and deletion.** On cancellation the Firm may export all Firm Data. We erase Firm Data 30 days after cancellation, including document bytes in object storage, except what we must keep by law (security audit trail).
11. **Records.** We keep a record of processing categories, sub-processors and security measures and make it available to the Firm on request.
12. **Audit.** Once a year, or after a breach, the Firm may request a written report of our controls; on-site or third-party audits may be agreed at the Firm's cost.
`;

/** Minimal Markdown → HTML for our own trusted documents (headings, paragraphs,
 *  bullet lists, pipe tables, bold, code, links, horizontal rules). Output is
 *  bound through Angular's sanitizer; the source is a compile-time constant. */
const plain = (s: string) => s.replace(/[*`]/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').trim();

/** The id of a "## " section heading. */
export function legalSlug(heading: string): string {
  return 'section-' + plain(heading).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

/** The document's sections, for the "On this page" list. */
export function legalToc(md: string): { id: string; text: string }[] {
  return md.split(/\r?\n/).filter((l) => /^##\s+/.test(l))
    .map((l) => l.replace(/^##\s+/, '')).map((t) => ({ id: legalSlug(t), text: plain(t) }));
}

export function renderMarkdown(md: string): string {
  const escapeHtml = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const inline = (s: string) =>
    escapeHtml(s)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, text, href) => {
        const safe = /^(https?:\/\/|\/|mailto:)/.test(href) ? href.replace(/\.md$/, '') : '#';
        const target = safe.startsWith('http') ? ' target="_blank" rel="noopener noreferrer"' : '';
        return `<a href="${safe}"${target}>${text}</a>`;
      });
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (/^---+$/.test(line.trim())) { out.push('<hr />'); i++; continue; }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      // Sections (##) get an id for the page's "On this page" list.
      const id = h[1].length === 2 ? ` id="${legalSlug(h[2])}"` : '';
      out.push(`<h${h[1].length}${id}>${inline(h[2])}</h${h[1].length}>`); i++; continue;
    }
    if (line.trim().startsWith('|')) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const cells = lines[i].trim().slice(1, -1).split('|').map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      const [head, ...body] = rows;
      out.push('<table><thead><tr>' + head.map((c) => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
        // data-label: on phones each row becomes a card that names its columns.
        + body.map((r) => '<tr>' + r.map((c, col) => `<td data-label="${escapeHtml(plain(head[col] ?? ''))}">${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>');
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, '')); i++; }
      out.push('<ul>' + items.map((t) => `<li>${inline(t)}</li>`).join('') + '</ul>');
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+\.\s+/, '')); i++; }
      out.push('<ol>' + items.map((t) => `<li>${inline(t)}</li>`).join('') + '</ol>');
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#|\||---|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) { para.push(lines[i].trim()); i++; }
    out.push(`<p>${inline(para.join(' '))}</p>`);
  }
  return out.join('\n');
}

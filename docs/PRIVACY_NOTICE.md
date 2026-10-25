# VidhiSangh Privacy Notice

**Version 2026-10-25 · Effective 25 October 2026**

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
| Sending **product updates on WhatsApp** (new features, about once or twice a month) | Consent, given separately and only if you say yes on the Home screen or switch on Settings → Notifications → "Product updates on WhatsApp". Each yes or no is recorded with the date and this notice's version. Withdraw by switching it off; no further updates are sent |
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

The retention job runs nightly (`infra/jobs/vidhisangh-retention.timer`). Periods are configurable by the operator and the current values are published at `/api/v1/privacy/notice`.

## 5. Your rights (s.11–s.14) and how to use them

| Right | How |
|---|---|
| **Access** (s.11) — a copy of everything we hold about you | Settings → Privacy & data → *Download my data* (JSON), or `GET /api/v1/privacy/me/export` |
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
| Meta Platforms (WhatsApp Business) | WhatsApp sign-in codes, hearing reminders if you turn them on, and product updates if you agree to them | Mobile number, the code, the list of next-day hearings, or your first name in an update |
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
| Postal address | *set via `VS_GRIEVANCE_OFFICER_ADDRESS`* |

The live values are shown on the [/privacy](https://vidhisangh.com/privacy) page and on every KYC form, and are returned by `GET /api/v1/privacy/notice`. If you have a grievance about a **firm's** handling of your data, contact that firm first; its data-protection contact is shown on its KYC form.

## 11. Security in brief

Argon2id password hashing, short-lived access tokens with rotating refresh tokens, optional MFA and passkeys, PostgreSQL row-level security for tenant isolation, field-level encryption for client identity data, TLS in transit, security-event audit trail. The full controls matrix is in `docs/SECURITY.md`.

## 12. Changes to this notice

We will publish a new version here with a new date, and existing users will be asked to review it on their next sign-in. Material reductions in your rights will never apply retroactively.

## 13. Breach notification

If a personal-data breach affects you, we will notify the Data Protection Board and you as required by s.8(6) and the rules made under it, describing what happened, what data was involved and what we are doing about it.

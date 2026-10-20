# VidhiSangh Terms of Service

**Version 2026-09-27 · Effective 27 September 2026**

These Terms govern your use of VidhiSangh (the "Service"), operated by VidhiSangh, India ("we", "us"). By creating an account you accept these Terms and the [Privacy Notice](PRIVACY_NOTICE.md) on behalf of yourself and, if you create an organisation, on behalf of that organisation (the "Firm"). The version you accepted and the time of acceptance are recorded against your account.

## 1. The Service

VidhiSangh provides practice management (matters, clients, documents, drafting, billing), legal research over public judgments, and a professional network for advocates, law firms and law students in India. Features vary by plan. We may improve, add or retire features with reasonable notice.

## 2. Eligibility and accounts

- You must be at least 18 and, where you hold yourself out as an advocate, enrolled with a State Bar Council.
- Keep your credentials confidential. Enable multi-factor authentication for accounts that hold client data. You are responsible for activity under your account until you tell us it is compromised.
- One e-mail address identifies one account on the platform.

## 3. Organisations, roles and administrators

The person who creates a Firm is its first **administrator** (`org_admin`). Administrators add users, assign roles and permissions, and may export or delete the Firm. The Firm is responsible for its users' compliance with these Terms. A Firm must keep at least one active administrator; an administrator who wants to leave must first make another user an administrator or delete the Firm.

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

We apply the controls described in `docs/SECURITY.md` (encryption at rest for client identity data, row-level tenant isolation, hashed credentials, audit trail, retention purges). You must report suspected security incidents to security@vidhisangh.com without undue delay.

## 10. Term, export and deletion

- **Your account**: you may delete it at any time from Settings → Privacy & data. It is anonymised immediately; see the Privacy Notice for what is retained and why.
- **The Firm**: an administrator may export everything (a zip of every table) and delete the Firm. Deletion disables every user at once and permanently erases all Firm data 30 days later. During those 30 days the Firm may ask us in writing to reinstate it.
- **By us**: we may terminate for material breach of Section 4 or non-payment. We will give the Firm 30 days to export its data unless the law or the safety of others prevents it.

## 11. Disclaimers and liability

The Service is provided "as is". We do not give legal advice and are not responsible for the outcome of any matter. To the extent permitted by law, our total liability to you for any claim in a year is limited to the fees the Firm paid us in the preceding twelve months. Nothing limits liability for fraud, death or personal injury, or breach of Schedule A caused by our gross negligence.

## 12. Governing law and disputes

These Terms are governed by the laws of India. Courts at New Delhi have exclusive jurisdiction, subject to any mandatory forum for consumer disputes. Data-protection complaints may also be made to the Data Protection Board of India.

## 13. Notices and contact

Legal notices: legal@vidhisangh.com. Privacy and grievances: the Grievance Officer named in the Privacy Notice and at `/privacy`. Security: security@vidhisangh.com.

---

## Schedule A — Data Processing Terms (Firm as Data Fiduciary, VidhiSangh as Data Processor)

1. **Scope.** This Schedule applies to personal data of clients, parties, leads, witnesses and other persons that the Firm stores in the Service ("Firm Data"). The Firm is the Data Fiduciary and VidhiSangh the Data Processor under the DPDP Act, 2023.
2. **Instructions.** We process Firm Data only to provide the Service as configured by the Firm and as documented in these Terms. The Firm's use of a feature (for example sending a KYC form) is its instruction to perform that processing.
3. **The Firm's obligations.** The Firm is responsible for having a lawful basis, for giving notice under s.5 to the persons concerned, for recording consent where consent is the basis (the Service supplies an append-only consent ledger for this), for recording verifiable guardian consent before processing a child's data, and for responding to rights requests. The Service provides export, correction, erasure (with legal-hold safeguards) and a request register to help it do so.
4. **Security (s.8(5)).** We maintain the technical and organisational measures in `docs/SECURITY.md`, including encryption of client identity data at rest, row-level tenant isolation, hashed tokens and credentials, TLS, audit logging and scheduled retention purges.
5. **Confidentiality.** Our personnel access Firm Data only to resolve a support request the Firm raises, under written confidentiality obligations, and every such access is logged.
6. **Sub-processors.** Listed in section 6 of the Privacy Notice. We will update the list before engaging a new sub-processor; the Firm may object within 30 days and terminate if we cannot resolve the objection.
7. **Location.** Firm Data is stored and processed in India.
8. **Breach.** We notify the Firm without undue delay, and in any case within 72 hours of confirming a personal-data breach affecting Firm Data, with the information the Firm needs to meet its own s.8(6) duties.
9. **Assistance.** We help the Firm respond to access, correction and erasure requests through the Service's export and erasure functions and, where needed, manual assistance at cost.
10. **Return and deletion.** On cancellation the Firm may export all Firm Data. We erase Firm Data 30 days after cancellation, including document bytes in object storage, except what we must keep by law (security audit trail).
11. **Records.** We keep a record of processing categories, sub-processors and security measures and make it available to the Firm on request.
12. **Audit.** Once a year, or after a breach, the Firm may request a written report of our controls; on-site or third-party audits may be agreed at the Firm's cost.

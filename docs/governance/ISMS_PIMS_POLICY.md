# Information security and privacy management policy

## Purpose and scope

VidhiSangh protects the confidentiality, integrity, availability and lawful processing of information used by its production service, personnel, suppliers and supporting systems. Scope includes source code, production infrastructure, databases, backups, legal corpora, customer documents, identity data, client portals, support and incident handling.

## Policy

1. Access is granted for an approved role, uses individual identities and least privilege, and is removed when no longer required.
2. Personal and confidential data is collected for stated purposes, limited to what is necessary, retained for approved periods and erased subject to legal holds.
3. Encryption is required in transit. Sensitive application fields and backups are encrypted at rest; production-volume and external-KMS migration remains a tracked risk until hosting capacity is available.
4. Every uploaded document is type/size checked and malware-scanned before storage. Scanner failure blocks the upload.
5. Security-relevant events, administrative changes, privacy actions and integration deliveries retain attributable audit evidence.
6. Changes are version-controlled, reviewed, tested and deployed through a repeatable process. Emergency changes receive retrospective review.
7. Vulnerabilities are triaged by severity. Critical exposure is contained immediately; high-risk corrective work receives priority over feature delivery.
8. Suppliers are assessed before receiving data or privileged access. Processing purpose, region, security measures, deletion, incident notice and sub-processing are recorded.
9. Incidents follow the documented response procedure, including containment, evidence preservation, impact assessment, notification decisions and lessons learned.
10. Continuity is supported by encrypted off-host backups, quarterly restore tests and documented recovery responsibilities.
11. Personnel complete security and privacy training and acknowledge confidentiality responsibilities.
12. Metrics, risks, incidents, requests, audit findings and overdue actions are reviewed by management on the stated cadence.

## Roles

- **Executive owner:** accepts residual business risk, supplies resources and chairs management review.
- **Grievance Officer:** oversees privacy notices, rights requests, grievances and escalation to counsel or the Data Protection Board.
- **Technical owner:** operates access, vulnerability, backup, monitoring, malware and change controls.
- **Users and suppliers:** follow access, confidentiality, acceptable-use and incident-reporting requirements.

Exceptions require a named owner, reason, compensating control and expiry date in the risk register. This policy is reviewed annually and after material legal, service or threat changes.

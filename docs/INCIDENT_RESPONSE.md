# VidhiSangh security incident and personal-data breach response

**Owner:** Information Security and Privacy Lead

**Last reviewed:** 27 September 2026
**Applies to:** production services, staff access, vendors, source code, backups and all personal data processed by VidhiSangh.

## Report and activate

Report suspected incidents immediately to `security@vidhisangh.com`. Privacy grievances and suspected personal-data breaches must also reach the appointed Grievance Officer configured through `VS_GRIEVANCE_OFFICER_*`. The incident lead opens a restricted incident record, assigns severity, preserves the first report verbatim and records every decision with a timestamp.

Activate this runbook for unauthorised access, tenant-isolation failure, credential or key exposure, malware, destructive activity, unavailable critical services, lost devices or backups, misdirected disclosures, or any suspected compromise of confidentiality, integrity or availability.

## First hour

1. **Triage:** record detection time, reporter, systems, data classes, tenants, users and jurisdictions that may be affected. Assign a lead and a separate scribe.
2. **Contain:** revoke affected sessions and API keys; disable accounts, webhooks or integrations; isolate hosts or storage; block indicators at nginx/firewall; rotate exposed secrets. Prefer reversible containment that preserves evidence.
3. **Preserve evidence:** copy relevant audit-chain results, application/nginx/system logs, database connection logs, alerts, configuration and a UTC timeline. Hash exported evidence and restrict access. Do not delete or modify the originals.
4. **Confirm tenant isolation:** query by tenant and object identifiers using the admin incident procedure; never disable RLS for convenience. Record the exact scope and evidence for every affected tenant.
5. **Escalate:** notify the product owner, security lead, privacy lead and legal counsel. Contact infrastructure and affected processors when their service or data is involved.

## Assess a personal-data breach

The privacy lead records the categories and approximate number of Data Principals and records affected; data sensitivity; encryption and key exposure; likely harm; geographic scope; duration; containment; and whether children or vulnerable individuals are involved. The decision on notification must cite the applicable DPDP Act and rules in force at the time and be reviewed by Indian privacy counsel.

Where notification is required, notify the Data Protection Board of India and affected Data Principals in the form and timeframe then prescribed. Use clear language covering what happened, likely consequences, measures taken, steps the individual can take, and the Grievance Officer contact. Record the legal decision even when notification is not required.

## Eradicate and recover

Remove the root cause, patch or reconfigure affected components, rotate relevant keys and credentials, validate the audit chain, and scan affected uploads and hosts. Restore only from a verified backup. Before reopening service, verify authentication, tenant isolation, document access, webhook destinations, security headers, monitoring and backup jobs. Maintain heightened monitoring for an incident-specific period.

## Close and learn

Within five working days of recovery, complete a blameless review containing the timeline, root cause, control failures, data and tenants affected, notification decisions, recovery evidence, customer communications, and assigned corrective actions with owners and dates. Add regression tests where code contributed, update the risk register and this runbook, and retain the incident record according to the security-log and legal-retention schedule.

## Prepared material

- Production and deployment procedures: [`DEPLOYMENT.md`](DEPLOYMENT.md)
- Implemented control evidence: [`SECURITY.md`](SECURITY.md)
- Finding-by-finding audit record: [`SECURITY_AUDIT_2026-09.md`](SECURITY_AUDIT_2026-09.md)
- Public-facing status wording: [`COMPLIANCE_STATUS.md`](COMPLIANCE_STATUS.md)
- Runtime evidence: tenant-scoped audit events, `/admin/audit/verify`, nginx/application logs, PostgreSQL connection logs and encrypted backup logs.

Run a tabletop exercise at least annually and after a material architecture or regulatory change. Record participants, scenario, decisions, gaps and follow-up actions.

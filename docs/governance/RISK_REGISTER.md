# Security and privacy risk register

Scale: likelihood and impact are 1–5; score is their product. Treatment status reflects evidence as at 27 September 2026.

| ID | Risk | L | I | Score | Current controls | Treatment / owner / target | Status |
|---|---|---:|---:|---:|---|---|---|
| R-01 | Loss of production database or documents | 2 | 5 | 10 | Nightly encrypted backup, local off-host copy, verified full restore | Add a second automated object-store copy; technical owner; when bucket is available | Open |
| R-02 | Host theft exposes active database/document volume | 3 | 5 | Field encryption, encrypted backups, restricted host access | Add provider-encrypted disk and external KMS; executive/technical owner; requires provider volume | Open |
| R-03 | Malicious uploaded document affects users or systems | 2 | 5 | MIME/size controls; ClamAV scan before storage; fail-closed startup/upload | Weekly signature/service review; technical owner | Treated |
| R-04 | Tenant data crosses an organisation boundary | 2 | 5 | Forced PostgreSQL RLS, tenant filters, least-privilege DB role, tests and audit log | Include in each internal audit and annual penetration test | Monitored |
| R-05 | Credential theft or account takeover | 3 | 5 | HttpOnly sessions, MFA/passkeys, lockout/rate limits, ES256, encrypted credentials | Complete separate peppers during maintenance; technical owner | Open |
| R-06 | Service/job failure is unnoticed | 2 | 4 | Health endpoint, systemd supervision, local failure log, encrypted-SMTP failure alert | Review alert delivery weekly and add external uptime monitoring | Treated / improve |
| R-07 | DNS single point takes service or mail offline | 3 | 4 | Two NS labels, DNS backups | Place secondary authority on another provider/IP and update glue; executive owner | Open |
| R-08 | Legal/privacy text is inaccurate or incomplete | 3 | 4 | Versioned notice/terms, named Grievance Officer, rights workflow | Add official postal address and Indian-counsel approval; privacy owner | Open |
| R-09 | Unknown application vulnerability is exploited | 3 | 5 | SAST/SCA workflows, headers, input controls, baseline DAST | Independent authenticated penetration test and retest; executive owner | Open |
| R-10 | Supplier processing or transfer lacks oversight | 3 | 4 | Published sub-processor list and supplier register | Collect contracts/DPA, region, deletion and incident terms before enabling each provider | Open |
| R-11 | Malware signatures become stale | 2 | 4 | `clamav-freshclam` automatic updates and fail-closed scanner dependency | Alert on updater/daemon failure and review signature date weekly | Treated |
| R-12 | Git changes bypass review or required checks | 3 | 4 | Private SSH remote and CI definitions | Enable protected `master`/required checks in GitLab admin; repository owner | Open |

Residual risk acceptance must be dated and signed in management-review minutes. “Open” does not mean no control exists; it means planned treatment or formal acceptance is incomplete.

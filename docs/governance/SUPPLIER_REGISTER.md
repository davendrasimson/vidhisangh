# Supplier and sub-processor register

| Supplier/service | Purpose and data | Region/transfer | Current technical controls | Required governance evidence | Status |
|---|---|---|---|---|---|
| Production hosting provider | Application, database, documents, logs and encrypted backups | Confirm contract and physical region | SSH keys, firewall, hardened services, field encryption, encrypted backup | Contract, DPA, incident SLA, deletion evidence, encrypted-volume/KMS option | Review open |
| Titan Mail | Transactional recipient identity and message content | Confirm Titan account region/terms | TLS SMTP, SPF, DKIM, DMARC; password in encrypted systemd credential | DPA/terms, retention, incident notice, sub-processors | Technical setup complete; governance review open |
| Razorpay, when enabled | Payer identity, invoice reference and amount | India/provider terms | Signed webhooks and server-side reconciliation | DPA/terms, retention and refund/support process | Conditional |
| Google/Microsoft/LinkedIn SSO, when enabled | Verified e-mail, name and provider subject ID | Provider-dependent | OAuth code + PKCE; no automatic account provisioning | Provider terms, DPA, transfer assessment | Conditional |
| Slack, per tenant when enabled | Notification text chosen by firm | Provider-dependent | Tenant-specific webhook, redacted delivery logs | Firm instruction, DPA/terms and content minimisation | Conditional |
| Future S3/KMS provider | Documents, court corpus and backups | Select India region | SSE-KMS support already implemented | Bucket/KMS policy, DPA, retention, versioning, replication and deletion evidence | Selection pending |

Before onboarding or materially changing a supplier, record the service owner, contract date, renewal date, processing role, countries, sub-processors, security evidence, breach-notice period, return/deletion terms and exit plan in the controlled firm copy of this register.

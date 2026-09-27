# VidhiSangh security and privacy status

**Status date:** 27 September 2026
**Public application page:** `/trust`

The September review recorded 65 security and privacy findings. All 65 have a remediation recorded in [`SECURITY_AUDIT_2026-09.md`](SECURITY_AUDIT_2026-09.md). The implemented controls are mapped to source, migrations, tests and infrastructure configuration in [`SECURITY.md`](SECURITY.md).

| Framework | Product status | Meaning |
|---|---|---|
| OWASP Top 10 (2021) | Assessed technical controls implemented | The application review covered access control, cryptography, injection, design, configuration, components, authentication, integrity, logging and SSRF. This is not an independent penetration-test attestation. |
| DPDP Act 2023 | Technical privacy controls implemented | Notice, consent, data-principal rights, grievance workflow, retention, erasure, encryption and breach-response procedures exist. Salil Shaida is the named Grievance Officer; postal-address completion and Indian-counsel review remain owner actions. |
| ISMS / ISO/IEC 27001:2022 | Control-aligned | Technical controls map to Annex A. Certification requires an operated management system, risk treatment, internal audit, management review and an accredited external audit. |
| PIMS / ISO/IEC 27701 | Control-aligned | Product privacy controls map to controller/processor responsibilities. Certification requires the wider privacy management programme and external audit. |

## Wording approved for the product

- “65 of 65 assessed security and privacy findings remediated.”
- “OWASP Top 10 and DPDP technical controls implemented.”
- “ISMS and PIMS control-aligned.”
- “See current status and operational dependencies.”

Do not publish “ISO certified”, “DPDP certified”, “fully compliant”, or similar language until the applicable legal review or accredited certification supplies evidence for that claim. Compliance is an ongoing operational state, not a one-time software feature.

## Operational dependencies still open

- Maintain the tested encrypted off-host local backup process and repeat its restore drill quarterly; add a second automated remote destination when object storage is available.
- Use encrypted production volumes and, when selected, external KMS/HSM custody.
- Complete the Grievance Officer postal address and counsel review of the Terms and Privacy Notice.
- Maintain the live Titan SMTP mailbox and delivery monitoring. MX, SPF, DKIM, DMARC and authenticated TLS from production were verified on 27 September 2026.
- Add independent secondary DNS and enable server-side branch protection. SNMPv2 has been disabled and UDP/161 is closed.
- Commission an independent penetration test/DAST and operate the ISMS/PIMS policy, risk, supplier, training, internal-audit and management-review cycle.

These dependencies are visible on the public Trust page so the product status remains accurate while the owner completes governance and infrastructure work.

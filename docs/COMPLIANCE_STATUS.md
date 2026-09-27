# VidhiSangh security and privacy status

**Status date:** 27 September 2026
**Public application page:** `/trust`

The September review recorded 65 security and privacy findings. All 65 have a remediation recorded in [`SECURITY_AUDIT_2026-09.md`](SECURITY_AUDIT_2026-09.md). The implemented controls are mapped to source, migrations, tests and infrastructure configuration in [`SECURITY.md`](SECURITY.md).

| Framework | Product status | Meaning |
|---|---|---|
| OWASP Top 10 (2021) | Assessed technical controls implemented | The application review covered access control, cryptography, injection, design, configuration, components, authentication, integrity, logging and SSRF. This is not an independent penetration-test attestation. |
| DPDP Act 2023 | Technical privacy controls implemented | Notice, consent, data-principal rights, grievance workflow, retention, erasure, encryption and breach-response procedures exist. Appointment of a named Grievance Officer and Indian-counsel review remain owner actions. |
| ISMS / ISO/IEC 27001:2022 | Control-aligned | Technical controls map to Annex A. Certification requires an operated management system, risk treatment, internal audit, management review and an accredited external audit. |
| PIMS / ISO/IEC 27701 | Control-aligned | Product privacy controls map to controller/processor responsibilities. Certification requires the wider privacy management programme and external audit. |

## Wording approved for the product

- “65 of 65 assessed security and privacy findings remediated.”
- “OWASP Top 10 and DPDP technical controls implemented.”
- “ISMS and PIMS control-aligned.”
- “See current status and operational dependencies.”

Do not publish “ISO certified”, “DPDP certified”, “fully compliant”, or similar language until the applicable legal review or accredited certification supplies evidence for that claim. Compliance is an ongoing operational state, not a one-time software feature.

## Operational dependencies still open

- Configure and restore-test an encrypted off-host backup destination.
- Use encrypted production volumes and, when selected, external KMS/HSM custody.
- Appoint and publish the named Grievance Officer; complete counsel review of Terms and Privacy Notice.
- Configure SMTP with DKIM and the matching SPF policy so rights and security messages reach users.
- Add independent secondary DNS, replace or disable SNMPv2, and enable server-side branch protection.
- Commission an independent penetration test/DAST and operate the ISMS/PIMS policy, risk, supplier, training, internal-audit and management-review cycle.

These dependencies are visible on the public Trust page so the product status remains accurate while the owner completes governance and infrastructure work.

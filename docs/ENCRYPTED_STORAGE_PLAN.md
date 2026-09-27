# Production encrypted-storage plan

**Assessed:** 27 September 2026

## Current state

The production VMware guest has one 100 GB virtual disk. `/var/lib/postgresql` and `/opt/vidhisangh/documents` are on the active root ext4/LVM filesystem. The volume group has no free extents and no second block device. Encrypting or shrinking that mounted production root filesystem in place would create an unacceptable data-loss and outage risk.

Application-level encryption remains active for sensitive fields. Production backups now use `age` asymmetric encryption: the server holds only the public recipient and the recovery identity is held off-host.

## Safe implementation

1. Add a provider-encrypted virtual disk sized for database growth and the planned corpus, or provision an encrypted managed database/object store.
2. Select external key custody: provider KMS/HSM for managed storage, or a LUKS2 key released by an external KMS during controlled boot. Do not place the only wrapping key on this VM.
3. Format and mount the new volume at temporary paths. Record key ID, recovery owners, rotation policy and emergency access procedure.
4. Take and verify an application-consistent encrypted backup.
5. Enter a maintenance window, stop the API and ingestion jobs, and perform a final database/document sync.
6. Move PostgreSQL and local document data, update mounts and configuration, then start PostgreSQL and the API.
7. Verify database integrity, application health, document reads/writes, backup execution and reboot-time key retrieval.
8. Retain the old disk only for the approved rollback window, then securely retire it through the provider.

## Completion evidence

- Provider or LUKS reports encryption enabled for every production data volume.
- The active key is identified by KMS/HSM key ID; rotation and recovery have named owners.
- A reboot and recovery exercise succeeds without storing plaintext keys on the VM.
- Database, documents and backup restore checks pass after migration.

**Status:** blocked on a second encrypted provider volume or managed-storage/KMS selection. No unsafe in-place conversion was attempted.


# Off-host backup and restore test — 27 September 2026

## Result

**Passed.** A new production backup was encrypted on the server, copied to the owner's local machine, decrypted with an off-host-only recovery identity, and restored into an isolated PostgreSQL cluster. The restored database matched production's key record counts and migration version.

## Backup set

- Production stamp: `20260927-1451` UTC
- Database archive: 2,222,996,402 bytes
- Database SHA-256: `39e439b27818f4b96902d8b434a6e925a07a77e12f31accbaedb892270036388`
- Document archive: 298 bytes (the local document store contained only its directory entry)
- Secrets archive: 10,440 bytes; its recovery key and public-recipient file are excluded by the backup script
- Encryption: `age` public-key encryption
- Key custody: production holds only `/opt/vidhisangh/.secrets/backup_age_recipients`; the private identity is mode `0600` under the owner's local backup directory and was not copied to the server or repository
- All three downloaded archives matched the SHA-256 values produced on the server

## Restore method

1. Copied the `.age` payloads and checksum files from the protected production backup directory to `/home/davendra-singh/VidhiSangh-backups/archive/20260927-1451/` using SSH/rsync.
2. Verified every encrypted payload against its server-generated SHA-256 value.
3. Decrypted the database locally and verified that `pg_restore --list` could read the archive: 709 non-comment TOC entries and 80 table-data sections.
4. Decrypted the document and secret streams without extracting them, and successfully listed their archive members.
5. Created a separate PostgreSQL 16.15 cluster under the local restore-test directory, on its own Unix socket and port `55432` with network listening disabled.
6. Restored the entire archive with four workers and checked the resulting schema, records, indexes, constraints and RLS metadata.
7. Stopped the test cluster. The temporary plaintext dump and restored cluster were removed after evidence was recorded; encrypted archives remain off-host.

## Evidence

| Check | Production before backup | Local restored value | Result |
|---|---:|---:|---|
| Alembic migration | `0052_audit_purge_guard` | `0052_audit_purge_guard` | Pass |
| Tenants | 1 | 1 | Pass |
| Users | 2 | 2 | Pass |
| Matters | 0 | 0 | Pass |
| Documents | 0 | 0 | Pass |
| Judgments | 5,901,405 | 5,901,405 | Pass |
| Invalid indexes | — | 0 | Pass |
| Unvalidated constraints | — | 0 | Pass |
| RLS-enabled tables | — | 47 | Pass |

- Full `pg_restore` duration: **1,086 seconds (18 minutes 6 seconds)**.
- Restored logical database size: **15 GB**. This can be smaller than the live database because a restore removes table/index bloat and excludes unrelated filesystem usage.
- The PostgreSQL service stopped cleanly after validation.

## Ongoing schedule and recovery objective

The local user timer `vidhisangh-offhost-backup.timer` is enabled and scheduled daily at 02:45 Asia/Kolkata, after the production backup window. It pulls the newest age-encrypted set, verifies checksums, retains 90 days locally and records `last-success`. A missed run is persistent and executes when the user's systemd session next starts.

Current demonstrated recovery time for the database restore step is approximately 19 minutes on this machine, excluding download time and application reconfiguration. Repeat a full restore quarterly and after material PostgreSQL, backup-format or storage changes. Add a second automated object-storage destination when the planned bucket is available so the local workstation is not the sole off-host copy.


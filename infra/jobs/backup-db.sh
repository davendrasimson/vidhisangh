#!/bin/bash
# ════════════════════════════════════════════════════════════════════
#  VidhiSangh — nightly backup (audit I-1)
#
#  What it does, in order, and it exits non-zero the moment any step fails:
#    1. pg_dump -Fc of the production database, streamed through
#       `pg_restore --list` so a partial/broken dump is detected BEFORE it
#       is kept (a dump that fails per-table under FORCE RLS still looks
#       plausible — see DEPLOYMENT.md "Backups — must run as the superuser").
#    2. Encrypt with `age` to the public keys in AGE_RECIPIENTS (preferred —
#       the host cannot decrypt its own backups) or, when age/recipients are
#       absent, openssl aes-256-cbc/pbkdf2 with the key file. The plaintext
#       dump lives only in a private tmp dir and is shredded on exit.
#    3. tar + encrypt the document store (VS_STORAGE_DIR) and .secrets.
#    4. Prune local copies older than RETENTION_DAYS (30).
#    5. Optional off-host copy with rclone when BACKUP_S3_URI is set.
#
#  Runs from backup-db.service (User=root — the ONE sanctioned superuser
#  use: only `postgres` can dump tables with FORCE ROW LEVEL SECURITY, and
#  the service drops to it via `sudo -u postgres` for pg_dump only).
#
#  Config (environment, all optional):
#    BACKUP_DIR         /opt/vidhisangh/backups
#    BACKUP_KEY_FILE    /opt/vidhisangh/.secrets/backup_key   (0600, root)
#    AGE_RECIPIENTS     /opt/vidhisangh/.secrets/backup_age_recipients (age public keys, one per line)
#    STORAGE_DIR        document store dir (read from backend/.env VS_STORAGE_DIR when unset)
#    RETENTION_DAYS     30
#    BACKUP_S3_URI      e.g. s3remote:vidhisangh-backups/db   (rclone remote; skipped when unset)
#    PGDATABASE         vidhisangh
# ════════════════════════════════════════════════════════════════════
set -euo pipefail
umask 077

BACKUP_DIR="${BACKUP_DIR:-/opt/vidhisangh/backups}"
BACKUP_KEY_FILE="${BACKUP_KEY_FILE:-/opt/vidhisangh/.secrets/backup_key}"
AGE_RECIPIENTS="${AGE_RECIPIENTS:-/opt/vidhisangh/.secrets/backup_age_recipients}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
PGDATABASE="${PGDATABASE:-vidhisangh}"
SECRETS_DIR="${SECRETS_DIR:-/opt/vidhisangh/.secrets}"
BACKEND_ENV="${BACKEND_ENV:-/opt/vidhisangh/backend/.env}"
STAMP="$(date -u +%Y%m%d-%H%M)"
DB_OUT="$BACKUP_DIR/db"
FILES_OUT="$BACKUP_DIR/files"
LOG="$BACKUP_DIR/backup.log"
WORK="$(mktemp -d)"
trap 'rc=$?; shred -u "$WORK"/* 2>/dev/null || true; rmdir "$WORK" 2>/dev/null || true; [ $rc -eq 0 ] || echo "!!! backup FAILED rc=$rc $(date -u +%FT%TZ)" | tee -a "$LOG" >&2; exit $rc' EXIT

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
die() { log "ERROR: $*"; exit 1; }

mkdir -p "$DB_OUT" "$FILES_OUT"
[ -r "$BACKUP_KEY_FILE" ] || [ -r "$AGE_RECIPIENTS" ] || die "no encryption key: create $BACKUP_KEY_FILE (0600) or $AGE_RECIPIENTS"

# ── Encryption: age with a recipients file (preferred), else openssl + key file ──
# age is asymmetric: the host only holds PUBLIC keys, so a compromised host
# cannot read its own backups; the private identity lives off-host.
encrypt() {  # stdin → stdout
  if command -v age >/dev/null 2>&1 && [ -r "$AGE_RECIPIENTS" ]; then
    age -R "$AGE_RECIPIENTS"
  else
    [ -r "$BACKUP_KEY_FILE" ] || die "openssl fallback needs $BACKUP_KEY_FILE"
    openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass "file:$BACKUP_KEY_FILE"
  fi
}
ENC_EXT=".enc"; command -v age >/dev/null 2>&1 && [ -r "$AGE_RECIPIENTS" ] && ENC_EXT=".age"

# ── 1. Database dump, verified before it is kept ─────────────────────
DUMP="$WORK/$PGDATABASE-$STAMP.dump"
log "pg_dump $PGDATABASE (as postgres, -Fc)"
# The work dir is root-private (umask 077), so postgres cannot open the file
# itself: pg_dump writes to stdout and root's shell owns the redirection.
sudo -u postgres pg_dump -d "$PGDATABASE" -Fc --no-owner --no-privileges > "$DUMP" \
  || die "pg_dump exited non-zero (partial dump discarded)"
[ -s "$DUMP" ] || die "dump is empty"
# A dump that pg_restore cannot list is corrupt; a dump whose TOC lacks the
# tenant tables is the RLS failure mode. Both are fatal.
TOC="$(pg_restore --list "$DUMP")" || die "pg_restore --list failed: dump is not readable"
log "dump bytes: $(stat -c %s "$DUMP"); TOC data sections: $(echo "$TOC" | grep -c 'TABLE DATA'); sample: $(echo "$TOC" | grep 'TABLE DATA' | head -2 | tr '\n' '|')"
for t in tenants users matters documents; do
  # No `grep -q` here: it exits on the first match, echo gets SIGPIPE and
  # `pipefail` turns a *successful* match into rc=141 (the TOC is >64 KiB).
  [ "$(echo "$TOC" | grep -cE "TABLE DATA public $t( |$)")" -gt 0 ] || die "dump has no data section for '$t' — RLS/permission failure?"
done
DUMP_SIZE=$(stat -c %s "$DUMP")
log "dump ok: $DUMP_SIZE bytes, $(echo "$TOC" | grep -c 'TABLE DATA') table data sections"

# ── 2. Encrypt ───────────────────────────────────────────────────────
DB_FINAL="$DB_OUT/$PGDATABASE-$STAMP.dump$ENC_EXT"
encrypt < "$DUMP" > "$DB_FINAL.part" || die "encryption failed"
mv "$DB_FINAL.part" "$DB_FINAL"
sha256sum "$DB_FINAL" > "$DB_FINAL.sha256"
log "encrypted → $DB_FINAL ($(stat -c %s "$DB_FINAL") bytes)"

# ── 3. Document store + secrets ──────────────────────────────────────
if [ -z "${STORAGE_DIR:-}" ] && [ -r "$BACKEND_ENV" ]; then
  STORAGE_DIR="$(grep -E '^VS_STORAGE_DIR=' "$BACKEND_ENV" | tail -1 | cut -d= -f2- | tr -d "\"'" || true)"
fi
if [ -n "${STORAGE_DIR:-}" ] && [ -d "$STORAGE_DIR" ]; then
  FILES_FINAL="$FILES_OUT/documents-$STAMP.tar.zst$ENC_EXT"
  log "archiving document store $STORAGE_DIR"
  tar -C "$(dirname "$STORAGE_DIR")" -cf - "$(basename "$STORAGE_DIR")" | zstd -q -T0 -3 | encrypt > "$FILES_FINAL.part" \
    || die "document store archive failed"
  mv "$FILES_FINAL.part" "$FILES_FINAL"
  sha256sum "$FILES_FINAL" > "$FILES_FINAL.sha256"
  log "documents → $FILES_FINAL ($(stat -c %s "$FILES_FINAL") bytes)"
else
  log "document store: VS_STORAGE_DIR not set or not a directory — skipped (S3 backend: enable bucket versioning + replication instead)"
fi

if [ -d "$SECRETS_DIR" ]; then
  SEC_FINAL="$FILES_OUT/secrets-$STAMP.tar$ENC_EXT"
  # The backup key itself is deliberately excluded: a backup must never contain the key that opens it.
  tar -C "$(dirname "$SECRETS_DIR")" --exclude="$(basename "$BACKUP_KEY_FILE")" --exclude="$(basename "$AGE_RECIPIENTS")" \
      -cf - "$(basename "$SECRETS_DIR")" | encrypt > "$SEC_FINAL.part" || die "secrets archive failed"
  mv "$SEC_FINAL.part" "$SEC_FINAL"
  sha256sum "$SEC_FINAL" > "$SEC_FINAL.sha256"
  log "secrets → $SEC_FINAL"
fi

# ── 4. Prune ─────────────────────────────────────────────────────────
PRUNED=$(find "$DB_OUT" "$FILES_OUT" -type f \( -name "*$ENC_EXT" -o -name "*.sha256" -o -name "*.enc" -o -name "*.age" \) -mtime +"$RETENTION_DAYS" -print -delete | wc -l)
log "pruned $PRUNED file(s) older than $RETENTION_DAYS days"

# ── 5. Off-host copy (optional) ──────────────────────────────────────
if [ -n "${BACKUP_S3_URI:-}" ]; then
  command -v rclone >/dev/null 2>&1 || die "BACKUP_S3_URI set but rclone is not installed"
  log "rclone copy → $BACKUP_S3_URI"
  rclone copy --transfers 2 --checksum --immutable "$DB_OUT" "$BACKUP_S3_URI/db" || die "rclone db copy failed"
  rclone copy --transfers 2 --checksum --immutable "$FILES_OUT" "$BACKUP_S3_URI/files" || die "rclone files copy failed"
  log "off-host copy ok"
else
  log "off-host copy: BACKUP_S3_URI unset — skipped (set an rclone remote to satisfy I-1 fully)"
fi

# Machine-readable success marker for monitoring (age of this file = RPO check).
date -u +%FT%TZ > "$BACKUP_DIR/last-success"
log "backup complete"

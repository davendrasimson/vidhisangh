#!/bin/bash
# ════════════════════════════════════════════════════════════════════
#  VidhiSangh — restore a backup into a FRESH database (audit I-1)
#
#    sudo infra/jobs/restore-db.sh /opt/vidhisangh/backups/db/vidhisangh-20260927-2000.dump.age [target_db]
#
#  Never restores over the live database. It creates `target_db`
#  (default: vidhisangh_restore_<stamp>), restores into it, re-applies the
#  role grants the app needs, and prints the row counts of the core tables
#  so the drill can be recorded. Promote by renaming databases only after
#  the checks pass (see DEPLOYMENT.md → Backups → "Restore drill").
#
#  Exits non-zero on any failure. Decrypts to a private tmp; shreds after.
# ════════════════════════════════════════════════════════════════════
set -euo pipefail
umask 077

SRC="${1:?usage: restore-db.sh <backup file> [target_db]}"
STAMP="$(date -u +%Y%m%d%H%M)"
TARGET="${2:-vidhisangh_restore_$STAMP}"
BACKUP_KEY_FILE="${BACKUP_KEY_FILE:-/opt/vidhisangh/.secrets/backup_key}"
AGE_IDENTITY="${AGE_IDENTITY:-/opt/vidhisangh/.secrets/backup_age_identity}"
APP_ROLE="${APP_ROLE:-vidhisangh_app}"
ADMIN_ROLE="${ADMIN_ROLE:-vidhisangh_admin}"
WORK="$(mktemp -d)"
trap 'rc=$?; shred -u "$WORK"/* 2>/dev/null || true; rmdir "$WORK" 2>/dev/null || true; exit $rc' EXIT

[ -r "$SRC" ] || { echo "not readable: $SRC" >&2; exit 1; }
[[ "$TARGET" =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "bad target db name" >&2; exit 1; }
if [ -f "$SRC.sha256" ]; then
  (cd "$(dirname "$SRC")" && sha256sum -c "$(basename "$SRC").sha256") || { echo "checksum mismatch" >&2; exit 1; }
fi

DUMP="$WORK/restore.dump"
case "$SRC" in
  *.age) if [ -r "$AGE_IDENTITY" ]; then age -d -i "$AGE_IDENTITY" -o "$DUMP" "$SRC";
         else AGE_PASSPHRASE="$(cat "$BACKUP_KEY_FILE")" age -d -o "$DUMP" "$SRC"; fi ;;
  *.enc) openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:$BACKUP_KEY_FILE" -in "$SRC" -out "$DUMP" ;;
  *.dump) cp "$SRC" "$DUMP" ;;
  *) echo "unknown backup extension: $SRC" >&2; exit 1 ;;
esac
pg_restore --list "$DUMP" >/dev/null || { echo "decrypted dump is not readable" >&2; exit 1; }

echo "== creating $TARGET (owner $ADMIN_ROLE)"
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -qc "CREATE DATABASE \"$TARGET\" OWNER \"$ADMIN_ROLE\" TEMPLATE template0 ENCODING 'UTF8'"
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d "$TARGET" -qc "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS pgcrypto;"

echo "== restoring (this can take a while for a 28 GB corpus)"
# --no-owner/--no-privileges: objects are owned by the connecting role; grants
# are re-applied explicitly below so the app role ends up exactly as in prod.
sudo -u postgres pg_restore -d "$TARGET" --no-owner --no-privileges --role="$ADMIN_ROLE" -j "${RESTORE_JOBS:-4}" "$DUMP"

echo "== re-applying app-role grants"
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d "$TARGET" -q <<SQL
GRANT CONNECT ON DATABASE "$TARGET" TO "$APP_ROLE";
GRANT USAGE ON SCHEMA public TO "$APP_ROLE";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$APP_ROLE";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "$APP_ROLE";
ALTER DEFAULT PRIVILEGES FOR ROLE "$ADMIN_ROLE" IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$APP_ROLE";
SQL

echo "== verification (record these in the drill log)"
sudo -u postgres psql -X -d "$TARGET" -At <<'SQL'
select 'alembic_version', version_num from alembic_version;
select 'tenants', count(*) from tenants;
select 'users', count(*) from users;
select 'matters', count(*) from matters;
select 'documents', count(*) from documents;
select 'judgments', count(*) from judgments;
select 'rls_forced_tables', count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and c.relforcerowsecurity;
SQL

echo "== done: database $TARGET is ready. Point a staging .env at it (VS_POSTGRES_DB=$TARGET) to smoke-test,"
echo "   then promote with:  ALTER DATABASE vidhisangh RENAME TO vidhisangh_old_$STAMP; ALTER DATABASE \"$TARGET\" RENAME TO vidhisangh;"

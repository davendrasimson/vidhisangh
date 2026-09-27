#!/bin/bash
# Pull the newest age-encrypted production backup to an independent machine.
# Usage: pull-offhost-backup.sh LOCAL_ARCHIVE_DIR [SSH_TARGET]
set -euo pipefail
umask 077

LOCAL_ARCHIVE_DIR="${1:?usage: $0 LOCAL_ARCHIVE_DIR [SSH_TARGET]}"
SSH_TARGET="${2:-vidhisangh}"
REMOTE_ROOT="/opt/vidhisangh/backups"

stamp="$({ ssh -o BatchMode=yes "$SSH_TARGET" \
  "sudo find '$REMOTE_ROOT/db' -maxdepth 1 -type f -name 'vidhisangh-*.dump.age' -printf '%f\n' | sort | tail -1"; } \
  | sed -nE 's/^vidhisangh-([0-9]{8}-[0-9]{4})\.dump\.age$/\1/p')"
[ -n "$stamp" ] || { echo "No age-encrypted production backup found" >&2; exit 1; }

destination="$LOCAL_ARCHIVE_DIR/$stamp"
mkdir -p "$destination"
chmod 700 "$LOCAL_ARCHIVE_DIR" "$destination"

rsync -a --partial --protect-args --rsync-path='sudo rsync' \
  "$SSH_TARGET:$REMOTE_ROOT/db/vidhisangh-$stamp.dump.age" \
  "$SSH_TARGET:$REMOTE_ROOT/db/vidhisangh-$stamp.dump.age.sha256" \
  "$SSH_TARGET:$REMOTE_ROOT/files/documents-$stamp.tar.zst.age" \
  "$SSH_TARGET:$REMOTE_ROOT/files/documents-$stamp.tar.zst.age.sha256" \
  "$SSH_TARGET:$REMOTE_ROOT/files/secrets-$stamp.tar.age" \
  "$SSH_TARGET:$REMOTE_ROOT/files/secrets-$stamp.tar.age.sha256" \
  "$destination/"

for checksum in "$destination"/*.sha256; do
  expected="$(awk '{print $1}' "$checksum")"
  payload="${checksum%.sha256}"
  actual="$(sha256sum "$payload" | awk '{print $1}')"
  [ "$actual" = "$expected" ] || { echo "Checksum mismatch: $payload" >&2; exit 1; }
done

# Keep 90 days locally. The private age identity is deliberately outside this tree.
find "$LOCAL_ARCHIVE_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +90 -print -exec rm -rf -- {} +
printf '%s %s\n' "$(date -u +%FT%TZ)" "$stamp" > "$LOCAL_ARCHIVE_DIR/last-success"
echo "Off-host backup verified: $destination"


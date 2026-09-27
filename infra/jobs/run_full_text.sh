#!/bin/bash
# Extract order text for the loaded High Courts, one court-year at a time,
# newest year first, at low CPU/IO priority, with a free-disk guard.
#
#   nohup infra/jobs/run_full_text.sh > /opt/vidhisangh/backups/full-text.log 2>&1 &
#
# Resumable: the extractor skips rows already done, so re-running after a stop
# just continues. Order of courts = order of value: Delhi (best-structured),
# P&H, Allahabad. Set COURTS / YEAR_FROM / MIN_FREE_GB to override.
set -euo pipefail
# Maintenance-role access for VACUUM/ANALYZE — never the postgres superuser (A-28).
# PGPASSFILE holds one line: localhost:5432:vidhisangh:vidhisangh_maint:<password>
# and the role has `GRANT MAINTAIN ON judgments` (PG17) — see DEPLOYMENT.md
# → "Maintenance role".
export PGPASSFILE="${PGPASSFILE:-/opt/vidhisangh/.secrets/pgpass_maint}"
PSQL=(psql -X -v ON_ERROR_STOP=1 -h "${PGHOST:-localhost}" -U "${PGMAINT_USER:-vidhisangh_maint}" -d "${PGDATABASE:-vidhisangh}")
cd /opt/vidhisangh/backend
# The bulk loaders need the owner role (they create partitions/indexes);
# only the VS_POSTGRES_* variables are exported, not the whole admin file.
while IFS="=" read -r k v; do case "$k" in VS_POSTGRES_*|VS_DATABASE_URL) export "$k=$v";; esac; done < <(grep -E "^VS_(POSTGRES_|DATABASE_URL)" ./.env.admin)

COURTS="${COURTS:-delhi phhc allahabad}"
YEAR_TO="${YEAR_TO:-$(date +%Y)}"
YEAR_FROM="${YEAR_FROM:-1950}"
MIN_FREE_GB="${MIN_FREE_GB:-12}"
WORKERS="${WORKERS:-3}"

free_gb() { df -BG --output=avail / | tail -1 | tr -dc '0-9'; }

# Never run beside another bulk updater of `judgments` (deadlocks — see DEPLOYMENT.md).
while pgrep -f "backfill_case_parties|backfill_filing_dates|after-parties.sh|extract-delhi-2024.sh" >/dev/null; do sleep 60; done

echo "=== full-text extraction start $(date -u +%FT%TZ) · courts: $COURTS · free $(free_gb) GB ==="
for court in $COURTS; do
  for ((year=YEAR_TO; year>=YEAR_FROM; year--)); do
    if (( $(free_gb) < MIN_FREE_GB )); then
      echo "!!! stopping: only $(free_gb) GB free (guard ${MIN_FREE_GB} GB) — $(date -u +%FT%TZ)"
      exit 2
    fi
    echo "--- $court $year · free $(free_gb) GB · $(date -u +%FT%TZ)"
    PYTHONPATH=$PWD nice -n 10 ionice -c2 -n7 .venv/bin/python -m app.scripts.extract_order_text \
      --courts "$court" --year-from "$year" --year-to "$year" --workers "$WORKERS" 2>&1 \
      | { grep -E "bundle_start|bundle_done|finished|Error|Traceback" || true; } | cut -c1-220
  done
  echo "=== $court complete $(date -u +%FT%TZ) — vacuum"
  "${PSQL[@]}" -qc "VACUUM (ANALYZE) judgments"
done
echo "=== all courts complete $(date -u +%FT%TZ) · free $(free_gb) GB ==="

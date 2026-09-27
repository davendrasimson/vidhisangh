#!/bin/bash
# Extract order text for the loaded High Courts, one court-year at a time,
# newest year first, at low CPU/IO priority, with a free-disk guard.
#
#   nohup infra/jobs/run_full_text.sh > /opt/vidhisangh/backups/full-text.log 2>&1 &
#
# Resumable: the extractor skips rows already done, so re-running after a stop
# just continues. Order of courts = order of value: Delhi (best-structured),
# P&H, Allahabad. Set COURTS / YEAR_FROM / MIN_FREE_GB to override.
set -u
cd /opt/vidhisangh/backend && set -a && . ./.env.admin && set +a

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
      | grep -E "bundle_start|bundle_done|finished|Error|Traceback" | cut -c1-220
  done
  echo "=== $court complete $(date -u +%FT%TZ) — vacuum"
  sudo -u postgres psql -d vidhisangh -qc "VACUUM (ANALYZE) judgments"
done
echo "=== all courts complete $(date -u +%FT%TZ) · free $(free_gb) GB ==="

#!/bin/bash
# Build the full model for the agreed target set, in order:
#   1. Uttarakhand  — new court: ingest -> parties -> filing dates -> text
#   2. Supreme Court — judgment text (SCR volumes, headnotes excluded), counsel
#   3. Delhi, P&H, Allahabad, Uttarakhand — order text, newest year first
#
#   nohup infra/jobs/run_target_set.sh > /opt/vidhisangh/backups/target-set.log 2>&1 &
#
# Sequential by design (bulk updaters of `judgments` deadlock together);
# every step is resumable, so re-running after a stop just continues.
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
export PYTHONPATH=$PWD
PY="nice -n 10 ionice -c2 -n7 .venv/bin/python"
free_gb() { df -BG --output=avail / | tail -1 | tr -dc '0-9'; }

while pgrep -f "backfill_case_parties|backfill_filing_dates|extract_order_text|extract_sc_text|ingest_hc_judgments|run_full_text.sh|run_new_court.sh" >/dev/null; do sleep 60; done

echo "=== target set start $(date -u +%FT%TZ) · free $(free_gb) GB ==="
echo; echo "### 1. Uttarakhand"
/opt/vidhisangh/infra/jobs/run_new_court.sh uttarakhand

echo; echo "### 2. Supreme Court text · $(date -u +%FT%TZ)"
$PY -m app.scripts.extract_sc_text --workers 3 2>&1 | { grep -E "rows_selected|progress|finished|Error|Traceback" || true; } | cut -c1-200

echo; echo "### 3. High Court order text · $(date -u +%FT%TZ)"
COURTS="delhi phhc allahabad uttarakhand" /opt/vidhisangh/infra/jobs/run_full_text.sh

echo; echo "=== target set complete $(date -u +%FT%TZ) · free $(free_gb) GB ==="

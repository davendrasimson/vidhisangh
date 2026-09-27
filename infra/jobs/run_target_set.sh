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
set -u
cd /opt/vidhisangh/backend && set -a && . ./.env.admin && set +a
export PYTHONPATH=$PWD
PY="nice -n 10 ionice -c2 -n7 .venv/bin/python"
free_gb() { df -BG --output=avail / | tail -1 | tr -dc '0-9'; }

while pgrep -f "backfill_case_parties|backfill_filing_dates|extract_order_text|extract_sc_text|ingest_hc_judgments|run_full_text.sh|run_new_court.sh" >/dev/null; do sleep 60; done

echo "=== target set start $(date -u +%FT%TZ) · free $(free_gb) GB ==="
echo; echo "### 1. Uttarakhand"
/opt/vidhisangh/infra/jobs/run_new_court.sh uttarakhand

echo; echo "### 2. Supreme Court text · $(date -u +%FT%TZ)"
$PY -m app.scripts.extract_sc_text --workers 3 2>&1 | grep -E "rows_selected|progress|finished|Error|Traceback" | cut -c1-200

echo; echo "### 3. High Court order text · $(date -u +%FT%TZ)"
COURTS="delhi phhc allahabad uttarakhand" /opt/vidhisangh/infra/jobs/run_full_text.sh

echo; echo "=== target set complete $(date -u +%FT%TZ) · free $(free_gb) GB ==="

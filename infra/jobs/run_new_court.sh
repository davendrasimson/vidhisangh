#!/bin/bash
# Load a High Court that is not in the library yet, end to end:
#   metadata (ingest) -> parties/counsel -> filing dates -> full text (newest first)
#
#   nohup infra/jobs/run_new_court.sh bombay > /opt/vidhisangh/backups/court-bombay.log 2>&1 &
#
# Court keys are the ones `ingest_hc_judgments --list-courts` prints. Needs
# roughly 4.8 KB per order for metadata+indexes and ~3.5 KB for text: the
# whole remaining set of 22 courts (~17-18M orders) is ~150 GB — check the
# free-disk guard before starting a large court. Steps are sequential because
# bulk updaters of `judgments` deadlock when run together.
set -euo pipefail
# Maintenance-role access for VACUUM/ANALYZE — never the postgres superuser (A-28).
# PGPASSFILE holds one line: localhost:5432:vidhisangh:vidhisangh_maint:<password>
# and the role has `GRANT MAINTAIN ON judgments` (PG17) — see DEPLOYMENT.md
# → "Maintenance role".
export PGPASSFILE="${PGPASSFILE:-/opt/vidhisangh/.secrets/pgpass_maint}"
PSQL=(psql -X -v ON_ERROR_STOP=1 -h "${PGHOST:-localhost}" -U "${PGMAINT_USER:-vidhisangh_maint}" -d "${PGDATABASE:-vidhisangh}")
court="${1:?usage: run_new_court.sh <court key>}"
cd /opt/vidhisangh/backend
# The bulk loaders need the owner role (they create partitions/indexes);
# only the VS_POSTGRES_* variables are exported, not the whole admin file.
while IFS="=" read -r k v; do case "$k" in VS_POSTGRES_*|VS_DATABASE_URL) export "$k=$v";; esac; done < <(grep -E "^VS_(POSTGRES_|DATABASE_URL)" ./.env.admin)

MIN_FREE_GB="${MIN_FREE_GB:-15}"
YEAR_FROM="${YEAR_FROM:-1950}"
YEAR_TO="${YEAR_TO:-$(date +%Y)}"
WORKERS="${WORKERS:-3}"
PY="nice -n 10 ionice -c2 -n7 .venv/bin/python"
export PYTHONPATH=$PWD

free_gb() { df -BG --output=avail / | tail -1 | tr -dc '0-9'; }
guard() {
  if (( $(free_gb) < MIN_FREE_GB )); then
    echo "!!! stopping before '$1': only $(free_gb) GB free (guard ${MIN_FREE_GB} GB)"; exit 2
  fi
}
step() { echo; echo "=== $court · $1 · free $(free_gb) GB · $(date -u +%FT%TZ)"; }

while pgrep -f "backfill_case_parties|backfill_filing_dates|extract_order_text|ingest_hc_judgments" >/dev/null; do sleep 60; done

# The bucket's court name (what rows carry in `court`) is only known after
# ingest; the parties backfill takes that exact value, so read it back.
guard ingest;  step "ingest metadata"
$PY -m app.scripts.ingest_hc_judgments --courts "$court" --year-from "$YEAR_FROM" --year-to "$YEAR_TO" 2>&1 \
  | { grep -E "files_selected|file_done|ingest_complete|Error|Traceback" || true; } | cut -c1-200
code=$($PY - "$court" <<'EOF'
import sys; from app.scripts.ingest_hc_judgments import COURTS; print(COURTS[sys.argv[1]][0])
EOF
)
name=$("${PSQL[@]}" -tA --set=code="$code" -c "select court from judgments where source_ref like :'code' || ':%' limit 1")
echo "    court value: '$name' (code $code)"

guard parties; step "parties / counsel / neutral citations"
$PY -m app.scripts.backfill_case_parties --court "$name" 2>&1 | { grep -E "finished|Error|Traceback" || true; } | cut -c1-200

guard filing; step "filing dates"
$PY -m app.scripts.backfill_filing_dates --courts "$court" --year-from "$YEAR_FROM" --year-to "$YEAR_TO" 2>&1 \
  | { grep -E "finished|Error|Traceback" || true; } | cut -c1-200

step "full text, newest year first"
for ((year=YEAR_TO; year>=YEAR_FROM; year--)); do
  guard "text $year"
  $PY -m app.scripts.extract_order_text --courts "$court" --year-from "$year" --year-to "$year" --workers "$WORKERS" 2>&1 \
    | { grep -E "bundle_done|finished|Error|Traceback" || true; } | cut -c1-200
done

step "vacuum analyze"
"${PSQL[@]}" -qc "VACUUM (ANALYZE) judgments"
echo "=== $court complete · free $(free_gb) GB · $(date -u +%FT%TZ)"

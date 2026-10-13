#!/usr/bin/env bash
# import.sh <wave-dir> <group-number> [model]: validate results-N.jsonl locally, then import on production.
# <model> is the model the writing agents actually ran on (default claude-fable-5-1); it is stored on every headnote.
set -euo pipefail
D=$1; N=$2; MODEL=${3:-claude-fable-5-1}; HERE=$(cd "$(dirname "$0")" && pwd)
"$HERE/../../backend/.venv-linux/bin/python" "$HERE/validate.py" "$D/results-$N.jsonl" "$D/group-$N.txt"
scp -q "$D/results-$N.jsonl" vidhisangh:/tmp/hn-import.jsonl
ssh vidhisangh 'cd /opt/vidhisangh/backend && set -a && . ./.env && set +a && PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ai_headnotes import --file /tmp/hn-import.jsonl --model '"$MODEL"' && PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ai_headnotes status; rm -f /tmp/hn-import.jsonl' 2>&1 | grep -v '^{'

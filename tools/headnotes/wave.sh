#!/usr/bin/env bash
# wave.sh <wave-name> [limit=110] [groups=12]
# Exports the next <limit> Supreme Court judgments without an AI headnote (newest first)
# from production into $HN_WORK/<wave-name>/ and splits them into balanced group-N.txt files.
set -euo pipefail
W=${HN_WORK:-/tmp/vs-headnotes}; Q=$W/$1; LIMIT=${2:-110}; G=${3:-12}
mkdir -p "$W"
ssh vidhisangh "cd /opt/vidhisangh/backend && set -a && . ./.env && set +a && rm -rf /tmp/hn-queue && PYTHONPATH=\$PWD .venv/bin/python -m app.scripts.ai_headnotes export --limit $LIMIT --out /tmp/hn-queue" 2>&1 | grep -v '^{' | tail -1
rm -rf "$Q"; scp -qr vidhisangh:/tmp/hn-queue "$Q"; ssh vidhisangh 'rm -rf /tmp/hn-queue'
cd "$Q" && python3 - "$G" <<'PY'
import json, sys
n = int(sys.argv[1]); q = json.load(open("queue.json"))
print(len(q), "judgments", q[0]["date"], "->", q[-1]["date"])
groups = [[] for _ in range(n)]; load = [0]*n
for item in sorted(q, key=lambda x: -x["chars"]):
    i = load.index(min(load)); groups[i].append(item["id"]); load[i] += item["chars"]
for i, g in enumerate(groups, 1):
    open(f"group-{i}.txt", "w").write("\n".join(g) + "\n")
PY
echo "ready: $Q"

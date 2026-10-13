"""Recover finished per-judgment drafts from agents that stopped early (e.g. session limit).

    backend/.venv-linux/bin/python tools/headnotes/salvage.py <wave-dir>
    tools/headnotes/import.sh <wave-dir> salvage <model>

Collects every valid draft in <wave-dir>/*/<id-prefix>.json and every row in any
results-N.jsonl, then asks production which of the wave's judgments already have a
headnote and drops those, so the salvage file never contains an already-imported id.
Spot-check one against its judgment before importing. Judgments without a valid
draft stay pending and are exported again by the next wave.
"""
import glob, json, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
from app.modules.research.schemas import AiHeadnoteContent

d = pathlib.Path(sys.argv[1])
ids = [l.strip() for f in sorted(d.glob("group-*.txt")) if "salvage" not in f.name for l in open(f) if l.strip()]
found = {}
for path in glob.glob(str(d / "*" / "*.json")):
    pre = pathlib.Path(path).stem
    match = [i for i in ids if i.startswith(pre)]
    if len(match) != 1:
        continue
    try:
        data = json.load(open(path)); data = data.get("headnote", data)
        AiHeadnoteContent.model_validate(data); found[match[0]] = data
    except Exception:
        pass
for f in d.glob("results-*.jsonl"):
    if "salvage" in f.name:
        continue
    for line in open(f):
        if line.strip():
            try:
                row = json.loads(line); AiHeadnoteContent.model_validate(row["headnote"])
                found.setdefault(row["id"], row["headnote"])
            except Exception:
                pass
sql = "select id from judgments where ai_headnote is not null and id in (" + ",".join(f"'{i}'" for i in ids) + ")"
out = subprocess.run(["ssh", "vidhisangh", f"sudo -u postgres psql -d vidhisangh -Atc \"{sql}\""], capture_output=True, text=True, check=True).stdout
already = {l.strip() for l in out.splitlines() if l.strip()}
keep = {k: v for k, v in found.items() if k not in already}
(d / "results-salvage.jsonl").write_text("".join(json.dumps({"id": k, "headnote": v}, ensure_ascii=False) + "\n" for k, v in keep.items()))
(d / "group-salvage.txt").write_text("\n".join(keep) + "\n")
print(f"wave {len(ids)} judgments | drafts found {len(found)} | already on production {len(already)} | salvaged {len(keep)}")

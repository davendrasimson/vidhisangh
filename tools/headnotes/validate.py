"""Validate a results file: python validate.py <dir>/results-N.jsonl <dir>/group-N.txt"""
import json, pathlib, sys, uuid
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
from app.modules.research.schemas import AiHeadnoteContent
path, group = sys.argv[1], sys.argv[2]
want = {l.strip() for l in open(group) if l.strip()}
seen = set()
for line in open(path):
    if line.strip():
        obj = json.loads(line); uuid.UUID(obj["id"])
        AiHeadnoteContent.model_validate(obj["headnote"]); seen.add(obj["id"])
print("valid lines:", len(seen), "| missing:", sorted(want - seen), "| unexpected:", sorted(seen - want))

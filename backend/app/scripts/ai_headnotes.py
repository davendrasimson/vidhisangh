"""Export Supreme Court judgments for AI headnote writing, and import the results.

No paid API is called. The workflow (see docs/AI_HEADNOTES.md):

  python -m app.scripts.ai_headnotes status
  python -m app.scripts.ai_headnotes export --limit 50 --out /tmp/hn-queue
      -> one <judgment_id>.txt per judgment (newest first) + queue.json
  ... a writer (e.g. a Claude Code session) reads each file and writes one JSON
      object per line to results.jsonl: {"id": "<judgment_id>", "headnote": {...}}
  python -m app.scripts.ai_headnotes import --file results.jsonl --model claude-opus-5-5
  python -m app.scripts.ai_headnotes import --file results.jsonl --model ... --dry-run

Import validates every line before writing anything; a bad line aborts the run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import uuid

from pydantic import ValidationError

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope
from app.modules.research.ai_headnotes import (
    HeadnoteImportError,
    apply_ai_headnote,
    done_count,
    export_queue,
    pending_count,
)
from app.modules.research.schemas import AiHeadnoteContent


async def _status() -> None:
    async with session_scope(bypass_rls=True) as session:
        print(f"done: {await done_count(session)}  pending: {await pending_count(session)}")


async def _export(limit: int, out: pathlib.Path, skip_file: pathlib.Path | None) -> None:
    skip = set()
    if skip_file and skip_file.exists():
        skip = {uuid.UUID(x) for x in json.loads(skip_file.read_text())}
    out.mkdir(parents=True, exist_ok=True)
    async with session_scope(bypass_rls=True) as session:
        items = await export_queue(session, limit, skip)
    queue = []
    for item in items:
        header = "\n".join([
            f"JUDGMENT ID: {item.id}",
            f"CITATION: {item.citation or '-'}",
            f"CASE: {item.case_name}",
            f"DATE: {item.judgment_date or '-'}",
            f"BENCH: {item.bench or '-'}",
            f"ACTS (index): {'; '.join(item.acts) or '-'}",
            "=" * 72,
        ])
        (out / f"{item.id}.txt").write_text(header + "\n" + item.text + "\n")
        queue.append({"id": str(item.id), "citation": item.citation, "date": item.judgment_date,
                      "chars": len(item.text)})
    (out / "queue.json").write_text(json.dumps(queue, indent=1))
    print(f"exported {len(queue)} judgments to {out}")


def _read_results(path: pathlib.Path) -> list[tuple[uuid.UUID, dict]]:
    rows = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            jid = uuid.UUID(obj["id"])
            AiHeadnoteContent.model_validate(obj["headnote"])
        except (ValueError, KeyError, ValidationError) as exc:
            raise SystemExit(f"{path}:{n}: invalid line: {exc}") from exc
        rows.append((jid, obj["headnote"]))
    return rows


async def _import(path: pathlib.Path, model: str, force: bool, dry_run: bool) -> None:
    rows = _read_results(path)
    print(f"{len(rows)} valid headnotes in {path}")
    if dry_run:
        return
    async with session_scope(bypass_rls=True) as session:
        for jid, content in rows:
            try:
                await apply_ai_headnote(session, jid, content, model=model, force=force)
            except HeadnoteImportError as exc:
                raise SystemExit(f"aborted, nothing written: {exc}") from exc
    print(f"imported {len(rows)} headnotes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    exp = sub.add_parser("export")
    exp.add_argument("--limit", type=int, default=50)
    exp.add_argument("--out", type=pathlib.Path, required=True)
    exp.add_argument("--skip-file", type=pathlib.Path, help="JSON list of ids already handed out")
    imp = sub.add_parser("import")
    imp.add_argument("--file", type=pathlib.Path, required=True)
    imp.add_argument("--model", required=True, help="model that wrote the headnotes, e.g. claude-opus-5-5")
    imp.add_argument("--force", action="store_true", help="overwrite existing AI headnotes")
    imp.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.cmd == "status":
        asyncio.run(_status())
    elif args.cmd == "export":
        asyncio.run(_export(args.limit, args.out, args.skip_file))
    else:
        asyncio.run(_import(args.file, args.model, args.force, args.dry_run))


if __name__ == "__main__":
    main()

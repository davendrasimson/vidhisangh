# Separate 1,000-order headnote assignment

Reserved on 22 October 2026 for a second session at the user's request.

Workspace: `/home/davendra-singh/git/VidhiSangh`

Assignment directory: `backups/orders/supreme-court-20261022/headnotes/secondary-1000-20261022/`

Coverage: **1,000 unique orders, 28 April 2023 through 10 May 2022**, in ten
batches of 100. Verified zero overlap with all 563 previously assigned IDs.
First ID: `8a183618-2aab-4030-ba24-f82b2fd5cf22`.
Last ID: `9ab66def-3e1c-4082-9375-2084ea76e72a`.

## Prompt to give the other session

Continue the separate **secondary-1000-20261022** Supreme Court headnote assignment. Read `docs/HEADNOTE_SECONDARY_1000.md` and the writing rules and schema in `docs/AI_HEADNOTES.md`. Work only on the exact 1,000 IDs in this assignment's `queue.json`, using its exported `<id>.txt` judgment bodies. Do not export a fresh queue or work on batch-0001 through batch-0005 or the older 528-item queue. Those belong to another session.

The assignment is divided into ten ordered batches of 100 in `batch-01` through `batch-10`. Work through them in order, resuming existing validated drafts. Save each original draft in that batch's `drafts/<id>.json`, as `{"id":"...","headnote":{...}}`, and maintain `progress.jsonl` and a brief checkpoint in the assignment's `PROGRESS.md`. Read each complete judgment body and actual relevant statutory clauses before drafting. Do not read or paraphrase reporter editorial headnotes. If a body is empty or incomplete, recover the judgment body from the local PDF listed in `index.csv` and document the recovery. Handle image-only tables, separate opinions, procedural outcomes and reserved questions accurately. Use the law and disposition in that judgment; do not import later developments.

Use no paid APIs. Do not spawn subagents unless the user expressly requests them in that session. Validate with `AiHeadnoteContent` from `backend/app/modules/research/schemas.py`. Before uploading each completed group of 100, check exact manifest coverage, uniqueness and individual-file equality, run the production import dry-run, then transactional import **without `--force`**, recording the actual writing model and verifying production contents afterward. Never upload a partial batch. If production already contains a headnote for an assigned ID, skip rewriting it, record the existing completion, and reconcile the batch before import; never overwrite it. The existing standing authorization permits continuing this assignment without repeated confirmation.

## Reservation and isolation

`tools/headnotes/reservations.json` records the existing assignment and this new assignment. `tools/headnotes/reserved-ids.json` is their combined exclusion list for future queue exports using `--skip-file`. Both sessions must honour those reservations. Do not reuse `tools/headnotes/wave.sh` unmodified: it exports without reservation exclusions and uses a shared temporary directory.

The new queue was exported from production with `ai_headnote IS NULL`, excluding all 563 unique IDs found in existing local queues and batch manifests. The reservation prevents overlap with those known assignments; any future session must also read this registry. This assignment itself does not change any production headnotes.

Use `index.csv` for case names, dates, citation, judgment body and local PDF paths. `SHA256SUMS` and `reservation-verification.json` provide the source and exclusion checks. Sources and draft work are kept in the permanent local archive, which is Git-ignored; the reservation registry and this handoff are repository files. If using a different checkout or machine, copy the assignment directory as well as the repository handoff files.

`source-recovery-needed.json` lists any exported bodies found empty during
packaging. Recover those from their PDFs before drafting; a present text file
does not itself establish that the judgment body is complete.

## Status

- **23 October 2026 — batch-01 complete and imported (100/100).** All bodies read in
  full; drafts in `batch-01/drafts/`, aggregate `batch-01/results.jsonl` (SHA256
  `3e3db9a86a824ba6fee2da78602e26a8ef372834b645e4f9c5c68cb73ca01b29`); production had no
  pre-existing headnotes for these IDs; dry-run 100 valid; non-force import wrote 100;
  readback verified model `claude-fable-5-1` on all 100. Production: 2,466 done, 35,900
  pending. Receipt `batch-01/import-receipt.json`. No paid API, no subagents.
- **23 October 2026 — batch-02 complete and imported (100/100).** All bodies read in
  full (one body, `b48e093d`, recovered from the local PDF; see
  `batch-02/source-recovery.json`); aggregate `batch-02/results.jsonl` (SHA256
  `d1634ccb167f712d13afaa3b60d58f27e155b00498d83b0e59678312b746e339`); no pre-existing
  headnotes; dry-run 100 valid; non-force import wrote 100; readback verified model
  `claude-fable-5-1` on all 100. Production: 2,866 done, 35,500 pending. Receipt
  `batch-02/import-receipt.json`. No paid API, no subagents.
- **24 October 2026 — batch-03 complete and imported (100/100).** All bodies read in
  full (two recovered: `d0e31c01` from the local PDF, `9923bee9` from the free order.law
  text view; see `batch-03/source-recovery.json`); aggregate `batch-03/results.jsonl`
  (SHA256 `e46f956eff6c4b0d8a475a0a8b618f44b3b3ce9aeec24bbc17c19dff9e437069`); no
  pre-existing headnotes; dry-run 100 valid; non-force import wrote 100; readback verified
  model `claude-fable-5-1` on all 100. Production: 3,166 done, 35,200 pending. Receipt
  `batch-03/import-receipt.json`. No paid API, no subagents.
- **25 October 2026 — batch-04 complete and imported (100/100).** All bodies read in
  full (four recovered or supplemented from local PDFs; see `batch-04/source-recovery.json`);
  aggregate `batch-04/results.jsonl` (SHA256
  `d08cea2ec57b47d9994ad63aca486301a05c94c950d983e08b6bb76f9d6ecdf3`); no pre-existing
  headnotes. Items 1–9 were drafted with `claude-fable-5-1` and items 10–100 with
  `claude-opus-5-5`, so the import was split by model (dry-runs 9 and 91 valid; non-force
  imports wrote 9 and 91; readback confirmed both models). Production: 3,666 done, 34,700
  pending. Receipt `batch-04/import-receipt.json`. No paid API, no subagents.
- **26 October 2026 — batch-05 complete and imported (100/100).** All bodies read in
  full (one, `c67d6b08` — EPFO v. Sunil Kumar B. — recovered from the local PDF; see
  `batch-05/source-recovery.json`); aggregate `batch-05/results.jsonl` (SHA256
  `d381d6bf7308c9beb949fd5adc70513377ae7527ae5ea7bd279d27c9321f4565`); no pre-existing
  headnotes; dry-run 100 valid; non-force import wrote 100; readback verified model
  `claude-opus-5-5` on all 100. Production: 3,866 done, 34,500 pending. Receipt
  `batch-05/import-receipt.json`. No paid API, no subagents.
- **26 October 2026 — batch-06 complete and imported (100/100).** All bodies read in
  full (four recovered from local PDFs — `ef875878`, `600dea85`, `37b5cc7b`, `6d52f084`;
  see `batch-06/source-recovery.json`); aggregate `batch-06/results.jsonl` (SHA256
  `14dde01470402a272765490675b6856fc5926f7c18a23da4a8107845a4d2855f`); no pre-existing
  headnotes; dry-run 100 valid; non-force import wrote 100; readback verified model
  `claude-opus-5-5` on all 100. Production: 4,266 done, 34,100 pending. Receipt
  `batch-06/import-receipt.json`. No paid API, no subagents.
- **27 October 2026 — batch-07 complete and imported (100/100).** All bodies read in
  full (one, `3e693392` — Har Naraini Devi — recovered from the local PDF; see
  `batch-07/source-recovery.json`); aggregate `batch-07/results.jsonl` (SHA256
  `bb82ad2bd478e6d84ec4841505691b77903ac126b95e340e506c583a7dcc04d3`); no pre-existing
  headnotes; dry-run 100 valid; non-force import wrote 100; readback verified model
  `claude-opus-5-5` on all 100. Production: 5,066 done, 33,300 pending. Receipt
  `batch-07/import-receipt.json`. No paid API, no subagents.
- **28 October 2026 — batch-08 complete and imported (100/100).** All bodies read in
  full (no PDF recovery needed); aggregate `batch-08/results.jsonl` (SHA256
  `808c2575f1a8fc8c6fff22de3e6d3ea22d12a3fd932b94082dce4885d92d7b38`); no pre-existing
  headnotes; dry-run 100 valid; non-force import wrote 100; readback verified model
  `claude-opus-5-5` on all 100. Production: 5,566 done, 32,800 pending. Receipt
  `batch-08/import-receipt.json`. No paid API, no subagents.
- **29 October 2026 — batch-09 complete and imported (100/100).** All bodies read in
  full (three — `b55947ee`, `c564b2df`, `393cc28b` — recovered from local PDFs; see
  `batch-09/source-recovery.json`); aggregate `batch-09/results.jsonl` (SHA256
  `2adf0156b30026e969d79c4725ab2ec3d6400be7a873dd487e19e199586e5cc7`), imported in three
  model segments (items 1–26 and 44–100 `claude-fable-5-1`, items 27–43 `claude-opus-5-5`);
  no pre-existing headnotes; dry-runs 26/17/57 valid; non-force imports wrote 100; readback
  verified 83 fable + 17 opus and three full records equal to the drafts. Production:
  5,666 done, 32,700 pending. Receipt `batch-09/import-receipt.json`. No paid API, no
  subagents.
- **29 October 2026 — batch-10 complete and imported (100/100); assignment finished.**
  All bodies read in full (five — `ca68f070`, `0295199f`, `c23a7d5e`, `672796e2`,
  `e3f850a7` — recovered from local PDFs; see `batch-10/source-recovery.json`);
  `batch-10/results.jsonl` (SHA256
  `39bf940caa532e9258e842317fc1b21592d072fa534d8e0199df25ec81c828da`), single model
  segment `claude-fable-5-1`; no pre-existing headnotes; dry-run 100 valid; non-force
  import wrote 100; readback verified `claude-fable-5-1` ×100 and all 100 stored records
  equal to the drafts. Production: 5,766 done, 32,600 pending. Receipt
  `batch-10/import-receipt.json`. No paid API, no subagents.
- **Status: 1,000/1,000 drafted, imported and read back (batches 01–10). Nothing left to
  resume in this assignment.** The assignment `PROGRESS.md` carries the final checkpoint.

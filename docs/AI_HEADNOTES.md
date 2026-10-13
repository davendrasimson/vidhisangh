# AI-generated headnotes for Supreme Court judgments

Every Supreme Court judgment with full text can carry an **AI-generated
headnote**, stored apart from the Court's own text (`judgments.ai_headnote`,
migration 0064). The API returns it with `ai_generated: true` and a label, and
the judgment page shows an "AI-generated" badge, the model that wrote it and the
date. Nothing is ever presented as an official or reporter's headnote.

No paid API is used. Headnotes are written in Claude Code sessions (or by any
writer that follows these rules) from exported files, then imported. Work runs
**newest judgment first** and is resumable.

## Workflow

On the server (`ssh vidhisangh`, then `cd /opt/vidhisangh/backend && set -a && . ./.env && set +a`):

```
PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ai_headnotes status
PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ai_headnotes export --limit 50 --out /tmp/hn-queue
```

Copy `/tmp/hn-queue` to the machine doing the writing. Each `<judgment_id>.txt`
holds a short header (id, citation, case, date, bench, indexed Acts) and the
judgment body. The body starts after any reporter's editorial headnote, so that
copyrighted text is never read or paraphrased (*Eastern Book Company v. D.B. Modak*, 2008).

Write `results.jsonl`: one line per judgment, `{"id": "<judgment_id>", "headnote": {…}}`.
Then copy it back and import:

```
PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ai_headnotes import --file results.jsonl --model claude-opus-5-5 --dry-run
PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ai_headnotes import --file results.jsonl --model claude-opus-5-5
```

Import validates every line first and aborts without writing if any line is
invalid, if a judgment is not a Supreme Court judgment, or if it already has an
AI headnote (unless `--force`). `--model` must name the model that actually wrote
the headnotes.

## Continuing in a new session (read this first)

The user has given a **standing go-ahead**: keep writing headnotes wave after
wave, newest first, without asking. **Never use the paid Anthropic API or any
paid service** — the user declined that cost. Work only through Claude Code
helper agents on the user's plan.

State on 08/10/2026 when the last session ended: all 214 judgments of 2026 done.
A 2025 wave (110 judgments, 12/12/2025 → 10/09/2025) was being written by 12
agents; those results may not have been imported. Nothing is lost: the queue is
driven by the database, so any judgment without a headnote is simply exported
again. Check with `status` below.

One wave, step by step (run from the repo root on the dev laptop, ssh alias `vidhisangh` works):

1. `ssh vidhisangh 'cd /opt/vidhisangh/backend && set -a && . ./.env && set +a && PYTHONPATH=$PWD .venv/bin/python -m app.scripts.ai_headnotes status'`
2. The old session's agents wrote to `/tmp/claude-1000/-home-davendra-singh-git-VidhiSangh/529a95ce-7018-468a-9482-6cdb77cd7873/scratchpad/w2025a/` (a copy of the queue is in `/tmp/vs-headnotes/w2025a/`). If `results-*.jsonl` files exist in either, import them first, using that folder as the wave dir: `tools/headnotes/import.sh <that-folder> <N>` for each N (a "already has an AI headnote" error just means it was imported; skip it).
3. `tools/headnotes/wave.sh <wave-name> 54 6` — exports the next 54 pending judgments to `/tmp/vs-headnotes/<wave-name>/` in 6 balanced groups. Keep waves at 6 agents: a 12-agent wave hit the plan's session limit on 08/10/2026 and every agent stopped before writing anything.
4. Launch 6 background `general-purpose` agents in one message, one per group, each with the prompt in [tools/headnotes/AGENT_PROMPT.md](../tools/headnotes/AGENT_PROMPT.md) (fill in the wave dir and group number).
5. As each agent finishes: `tools/headnotes/import.sh /tmp/vs-headnotes/<wave-name> <N> <model>` where `<model>` is the model the agents ran on (shown by `/model`; default claude-fable-5-1). Read the agent's doubts; if it asks for a check, read the cited paragraph and confirm the held point matches before importing.
6. After the wave, add a row to the progress log below, then start the next wave.
7. If agents stop early ("You've hit your session limit"), recover their finished drafts: `backend/.venv-linux/bin/python tools/headnotes/salvage.py <wave-dir>` (it collects every valid draft and partial results file, and asks production which ids already have a headnote so nothing is imported twice), spot-check one, then `tools/headnotes/import.sh <wave-dir> salvage <model>`. Wait for the limit to reset before the next wave. Everything else stays pending and is re-exported. The limit has been hit after roughly 4–5 three-agent waves in a row (about 110–130 judgments); expect it every few hours.

Sizes still to go (judgments with full text): 2025 ≈ 897 (about 8 waves), 2024 ≈ 782, 2023 ≈ 856, then earlier years; 38,152 in total after 2026.
A wave of 12 agents uses roughly 2.6M tokens of plan usage and takes 5–10 minutes.

## The headnote format

```json
{
  "summary": "One or two plain sentences: what the Court decided and why.",
  "issues": ["Each question of law or fact the Court had to answer."],
  "provisions": [
    {"act": "Code of Civil Procedure, 1908", "provision": "Order VII Rule 11",
     "how_applied": "How the Court read and applied this clause in this case.",
     "paragraphs": ["14", "15"]}
  ],
  "held": [
    {"point": "Each holding, stated as the rule the Court laid down or applied.", "paragraphs": ["18"]}
  ],
  "result": "Appeal allowed; impugned order set aside; matter remitted to the High Court."
}
```

Limits (enforced on import): summary 20–900 characters; 1–8 issues; up to 12
provisions; 1–10 held points; no extra keys.

## Writing rules

1. **Read the whole judgment body first.** Do not write from the opening paragraphs alone.
2. **Read the relevant clause before applying it.** For every statutory provision
   the Court construes or applies, read the provision's actual text before
   writing about it: as the judgment quotes it, or, if the judgment does not quote
   it and the Act is in the bare-acts library (`frontend/public/bare-acts/text/`,
   25 central Acts such as BNS, BNSS, BSA, IPC, CrPC, CPC, Evidence, Contract,
   Limitation, Arbitration, NI, IBC, RERA, Consumer Protection), read the section
   there. Record each provision in `provisions` with the paragraphs where the
   Court deals with it. Only then write the `held` points.
3. **Ground every holding in the text.** Each `held` point and each provision
   cites the paragraph numbers where the Court says it. If the judgment has no
   paragraph numbers, leave `paragraphs` empty rather than guess.
4. **Own words.** Write original sentences. Short quotations of a statute or of
   the Court are fine; never reproduce long passages.
5. **No outside knowledge presented as the holding.** Do not add later
   developments, overruling, or general law the Court did not state.
6. **Short orders.** If the Court decided no question of law (adjournment,
   withdrawal, compromise, dismissal in limine without reasons), say so in one
   held point, for example "No question of law was decided; the appeal was
   dismissed as withdrawn with liberty to approach the High Court."
7. **Result** states the disposal and any directions (remand, costs, time limits).
8. **Neutral and precise.** Use the parties' roles (appellant, respondent, State)
   rather than characterising them; keep Indian legal usage (FIR, SLP, chargesheet).

## Progress log

| Date | Judgments written | Newest → oldest covered | Model |
|---|---|---|---|
| 08/10/2026 | 50 | 12/08/2026 → 19/05/2026 | claude-opus-5-5 (5 Claude Code agents, 10 each; two spot-checked against the text) |
| 08/10/2026 | 164 | 19/05/2026 → 05/01/2026 (all of 2026 complete: 214) | claude-opus-5-5 (17 agents; flagged passages re-checked) |
| 08/10/2026 | 54 | 12/12/2025 → 08/10/2025 (wave w2025a) | claude-opus-5-5 (6 agents) |
| 08/10/2026 | 26 | from wave w2025b (08/10/2025 → 11/09/2025), salvaged after the session limit stopped the agents | claude-opus-5-5 |
| 08/10/2026 | 27 | 08/10/2025 → 12/09/2025 (wave w2025c; 2025 now complete back to 11/09/2025) | claude-opus-5-5 (3 agents) |
| 08/10/2026 | 27 | 12/09/2025 → 01/09/2025 (wave w2025d) | claude-fable-5-1 (3 agents) |
| 08/10/2026 | 27 | 01/09/2025 → 22/08/2025 (wave w2025e) | claude-fable-5-1 (3 agents) |
| 08/10/2026 | 27 | 22/08/2025 → 14/08/2025 (wave w2025f) | claude-fable-5-1 (3 agents) |
| 08/10/2026 | 27 | 14/08/2025 → 06/08/2025 (wave w2025g) | claude-fable-5-1 (3 agents) |
| 08/10/2026 | 27 | 06/08/2025 → 30/07/2025 (wave w2025h) | claude-fable-5-1 (3 agents) |
| 08/10/2026 | 27 | 30/07/2025 → 21/07/2025 (wave w2025i) | claude-fable-5-1 (3 agents) |
| 08/10/2026 | 27 | 21/07/2025 → 15/07/2025 (wave w2025j) | claude-fable-5-1 (3 agents) |
| 08/10/2026 | 27 | 15/07/2025 → 06/06/2025 (wave w2025k) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 05/06/2025 → 23/05/2025 (wave w2025l) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 22/05/2025 → 18/05/2025 (wave w2025m) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 16/05/2025 → 13/05/2025 (wave w2025n) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 13/05/2025 → 07/05/2025 (wave w2025o) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 14 | from wave w2025p (06/05/2025 → 30/04/2025): group 1 plus 7 salvaged drafts after the session limit | claude-fable-5-1 |
| 09/10/2026 | 27 | 06/05/2025 → 29/04/2025 (wave w2025q, incl. the 11 left over from w2025p) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 29/04/2025 → 23/04/2025 (wave w2025r) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 23/04/2025 → 21/04/2025 (wave w2025s) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 15 | from wave w2025t (21/04/2025 → 14/04/2025): salvaged after the session limit stopped all three agents | claude-fable-5-1 |
| 09/10/2026 | 27 | 21/04/2025 → 07/04/2025 (wave w2025u, incl. the 12 left over from w2025t) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 07/04/2025 → 01/04/2025 (wave w2025v) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 01/04/2025 → 26/03/2025 (wave w2025w) | claude-fable-5-1 (3 agents) |
| 09/10/2026 | 27 | 26/03/2025 → 18/03/2025 (wave w2025x) | claude-fable-5-1 (3 agents) |
| 10/10/2026 | 27 | 17/03/2025 → 03/03/2025 (wave w2025y) | claude-fable-5-1 (3 agents) |
| 10/10/2026 | 27 | 03/03/2025 → 27/02/2025 (wave w2025z) | claude-fable-5-1 (3 agents) |
| 10/10/2026 | 27 | 27/02/2025 → 18/02/2025 (wave w2025aa) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 17/02/2025 → 11/02/2025 (wave w2025ab) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 11/02/2025 → 03/02/2025 (wave w2025ac) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 03/02/2025 → 29/01/2025 (wave w2025ad) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 29/01/2025 → 20/01/2025 (wave w2025ae) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 20/01/2025 → 08/01/2025 (wave w2025af) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 08/01/2025 → 01/01/2025 (wave w2025ag) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 01/01/2025 → 19/12/2024 (wave w2024a; all of 2025 complete) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 19/12/2024 → 13/12/2024 (wave w2024b) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 13/12/2024 → 09/12/2024 (wave w2024c) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 09/12/2024 → 25/11/2024 (wave w2024d) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 24/11/2024 → 14/11/2024 (wave w2024e) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 13/11/2024 → 05/11/2024 (wave w2024f; incl. AMU 7-judge, Article 39(b) 9-judge, CORE 5-judge) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 05/11/2024 → 21/10/2024 (wave w2024g; incl. industrial alcohol 9-judge) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 21/10/2024 → 04/10/2024 (wave w2024h; incl. Section 6A Citizenship 5-judge) | claude-opus-5-5 (3 agents) |
| 10/10/2026 | 27 | 04/10/2024 → 24/09/2024 (wave w2024i) | claude-opus-5-5 (3 agents) |
| 11/10/2026 | 27 | 24/09/2024 → 10/09/2024 (wave w2024j) | claude-opus-5-5 (3 agents) |
| 11/10/2026 | 27 | 10/09/2024 → 02/09/2024 (wave w2024k) | claude-opus-5-5 (3 agents) |
| 11/10/2026 | 27 | 30/08/2024 → 22/08/2024 (wave w2024l) | claude-opus-5-5 (3 agents) |
| 11/10/2026 | 27 | 22/08/2024 → 08/08/2024 (wave w2024m) | claude-opus-5-5 (3 agents) |
| 11/10/2026 | 27 | 08/08/2024 → 25/07/2024 (wave w2024n; incl. SC sub-classification 7-judge, mineral royalty 9-judge) | claude-opus-5-5 (3 agents) |

Next run: `export --limit 50` continues from 19/05/2026 backwards automatically. Writers should note, not resolve, internal inconsistencies in a judgment (conflicting dates, figures or paragraph references); the first run met several and left the disputed detail out of the headnote.

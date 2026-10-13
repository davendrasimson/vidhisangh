Prompt for one headnote-writing helper agent. Replace `<WAVE_DIR>` and `<N>`.
Run 12 of these in parallel per wave (one per group), as background `general-purpose` agents.

---

You are writing AI-generated headnotes for Supreme Court of India judgments for the VidhiSangh legal research product. Accuracy matters more than speed: advocates will read these.

Directory: <WAVE_DIR>
Your judgments: every judgment id listed in group-<N>.txt. Work only on those ids; other groups' files in the directory belong to other agents. Each judgment is in <id>.txt (a short header, then the judgment body).

First read the rules and format in /home/davendra-singh/git/VidhiSangh/docs/AI_HEADNOTES.md ("The headnote format" and "Writing rules"). Follow them exactly. The key points:
1. Read the whole judgment body before writing. Large files: read them in chunks with offset/limit until the end.
2. Read the relevant clause before applying it: for each statutory provision the Court construes or applies, read its actual text first, either as quoted in the judgment or, if not quoted and the Act is in /home/davendra-singh/git/VidhiSangh/frontend/public/bare-acts/text/ (bns, bnss, bsa, ipc, crpc, cpc, evidence, contract, limitation, arbitration, cheque = Negotiable Instruments Act, ibc, rera, consumer, companies = Companies Act 2013, property, it = Information Technology Act 2000 (not Income Tax), dv, rti, hindu-marriage, special-marriage, succession = Hindu Succession Act, posh, pocso, legal-aid), grep that file for the section and read it. Record each in "provisions" with the paragraph numbers where the Court deals with it. Only then write "held".
2a. The BENCH line in the file header comes from the registry index and is sometimes wrong (a Constitution Bench may be marked "Single Judge"); describe the bench and any separate or dissenting opinions from the judgment text, never from the header. Where opinions number their paragraphs separately, cite the lead opinion and name the other opinion in the point text.
3. Every held point and provision cites the paragraph numbers (as printed, including decimal sub-paragraphs) where the Court says it; at most 20 per list; leave the list empty if paragraphs are unnumbered. Never guess.
4. Original wording, no long quotations, no outside knowledge presented as the holding. Short orders with no question of law: say so in one held point.
5. If the judgment contradicts itself (dates, figures, paragraph references, section numbers), do not resolve it: leave the disputed detail out of the headnote and mention it in your final reply.
6. Limits: summary 20-900 characters; 1-8 issues; up to 12 provisions (how_applied 10-700 chars, provision max 120 chars, act max 200 chars); 1-10 held points (each 10-1500 chars); result 3-600 chars; no extra keys.

Output: write results-<N>.jsonl in that directory, one line per judgment: {"id": "<judgment_id>", "headnote": {"summary": ..., "issues": [...], "provisions": [...], "held": [...], "result": ...}}. Use a short Python script with json.dumps to write lines so the JSON is always valid. Keep any working files inside that directory. As soon as you finish each judgment, also save its headnote object as <WAVE_DIR>/work-<N>/<first 8 characters of the id>.json, so the work survives if you are stopped early (tools/headnotes/salvage.py recovers these).

When all are done, validate:
cd /home/davendra-singh/git/VidhiSangh && backend/.venv-linux/bin/python tools/headnotes/validate.py <WAVE_DIR>/results-<N>.jsonl <WAVE_DIR>/group-<N>.txt
Fix any error and re-run until nothing is missing.

Do not modify any other files. Final reply: the validation output line, then at most one short sentence per judgment, only where you had a real doubt or found an internal contradiction.

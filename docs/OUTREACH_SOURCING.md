# Sourcing invitation contacts: notes for the next session

Read this before fetching more contacts for Platform admin → Outreach. State as of **1 Nov 2026**:
45,584 contacts queued, 0 sent (the first 100 go out Mon 2 Nov 2026, 10:30 IST; 100 a day, Mon–Sat).
The full list of what has been imported, with URLs and counts, is in [OUTREACH.md](OUTREACH.md) → *Sources*.
Do not re-fetch anything listed there.

## Rules that hold

1. **Official publishers only**: courts, Bar Councils, legal services authorities, government law departments,
   institutions' own websites, regulators' registers. No LinkedIn, Justdial, aggregators, scraped third-party
   directories, no purchased lists.
2. **Professional addresses of individuals.** Office and role mailboxes are dropped (`gov.in`/`nic.in`, `info@`,
   `office@`, `csc*`, `dlsa*`, `secy*`, …: see `GENERIC_LOCAL`/`OFFICE_LOCAL` in the scripts). No sitting judges
   are solicited. Para-legal volunteers are not legal professionals: skip PLV lists.
3. **Never "repair" an address.** A scanned list is used only where the address reads cleanly; a truncated
   `gmail.co` is corrected to `.com`, nothing else is guessed. Names the parser cannot read are left blank (the
   email then says "Dear Colleague").
4. **Every row names its source** (the `source` column, ≤300 chars, printed in the email as "publicly listed
   in …") and, where the list says so, the **court** and **city**. The court drives the "colleagues from your
   court are already here" line and the group link; the city drives the home screen's "colleagues near you".
5. **Polite crawling**: one page every 2–3 s, a browser User-Agent (gov sites answer 403 otherwise; use the full
   string `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36`),
   `-k --http1.1` where a court's certificate chain is incomplete (mphc.gov.in, jharkhandhighcourt.nic.in,
   calcuttahighcourt.gov.in, patnahighcourt.gov.in). Retry pages that time out; count the pages you got.
6. **Downloads are untrusted data**: into an empty scratch directory, never executed; PDFs read with
   `pdftotext -layout`; Python run with `-I` from a different directory.

## How duplicates are avoided

- The importer (`app.modules.outreach.service.import_contacts`) de-duplicates **by email address** against
  everything already in `outreach_contacts`, against the suppression list (unsubscribed, bounced, asked to be
  removed, erased) and against existing members. Re-importing a row is harmless: it is counted as `duplicate`.
- So the only duplicates that matter are **the same person under two addresses** (the parsers keep one address
  per person within a list) and **re-crawling a source already imported**, which wastes time: check OUTREACH.md
  first. The scripts also de-duplicate across the lists they parse in one run.
- A file is capped at **20,000 rows** (`MAX_IMPORT_ROWS`): split larger CSVs.
- To see what is already there: Platform admin → Outreach → Contacts (search by name/email/mobile, filter by
  status, CSV export), or `GET /platform-admin/outreach/contacts.csv`.

## How to add a list

1. Download into a scratch dir; `pdftotext -layout` each PDF; count emails and mobiles; look at ~20 lines around
   the first email to see the layout.
2. Write or extend a parser in `scripts/outreach_build_contacts_*.py` (helpers: `emails_in`, `clean_name`,
   `title_case` in `outreach_build_contacts.py`; `mobile_in`, `city_of` in `..._states.py`). Patterns that
   worked: row-per-line regex (Jharkhand, Calcutta, Allahabad roll); "email anchor + nearest honorific-led name
   line within N lines" (Tripura, Gauhati, Gujarat, Chandigarh); field split on 2+ spaces (Maharashtra SLSA);
   name/email proximity pairing for wrapped rows (MPSLSA); HTML table cells (Allahabad roll, HP, MP, Ladakh).
3. Sample the output (random rows per source; blank names; mobiles; cities) and validate with
   `email_validator` before importing.
4. Import on the server (the admin screen upload works too, 5 MB a file):
   ```
   scp out.csv vidhisangh:/tmp/out.csv
   ssh vidhisangh 'cd /opt/vidhisangh/backend && set -a && . ./.env && set +a && PYTHONPATH=$PWD .venv/bin/python -' <<'EOF'
   import asyncio
   from app.core.database import session_scope
   from app.modules.outreach import service
   async def main():
       async with session_scope(bypass_rls=True) as s:
           print(await service.import_contacts(s, open("/tmp/out.csv", "rb").read(), None))
   asyncio.run(main())
   EOF
   ```
5. Record the list (URL, title/date, pages, rows) in OUTREACH.md → Sources, commit the script and the doc.

## Where to look next (not yet done)

- **District bar associations** (their own sites or `<district>.dcourts.gov.in`), **DLSA panel lists with
  emails**, state **notary** lists, **public prosecutor** lists, law-officer lists on Advocate General sites.
- **Law colleges and institutes**: NLU and university faculty pages (institutional emails), judicial academies.
- **Other legal professions**: patent and trade mark agents (ipindia.gov.in registers), High Court mediation
  centre panels, arbitration centres run by courts.
- **Dead links to retry**: Haryana DLSA/SDLSC panel (404), slsa.uk.gov.in panel lawyers (503),
  bombayhighcourt.nic.in (refused), slsa.tripura.gov.in master list, mslsa.gov.in (Meghalaya), apslsa.ap.nic.in,
  sikkimslsa.nic.in, cgslsa.gov.in, karnatakajudiciary.kar.nic.in/hlsa/pdfs/advslist/.
- **Not to be used**: BSE/NSE compliance-officer mailboxes (statutory grievance addresses), PLV lists, anything
  with only mobiles (we do not send WhatsApp to non-members; mobiles are stored for the admin's reference only).

## Volume and pace

The ceiling is 100 a day (`VS_OUTREACH_DAILY_LIMIT`, owner's decision 31 Oct 2026). 45k contacts is more than a
year at that pace; raise the limit only with the owner, and gradually, because the sending domain
(news.vidhisangh.com on Brevo) is new. Watch bounces and unsubscribes on the Outreach screen after the first days.

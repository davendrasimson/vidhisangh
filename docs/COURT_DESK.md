# Court desk — each court's cause lists, for its members

Built 16 November 2026 after the owner asked for "a daily cause list and court
details, without using any personal data, for their respective courts". Code:
`backend/app/modules/courts/` (`registry.py`, `fetch.py`, `service.py`), job
`app/scripts/court_desk.py`, units `infra/jobs/vidhisangh-court-desk.{service,timer}`,
migration `0091` (`court_cause_lists`), card on the Daily page
(`frontend/src/app/features/daily/`).

## No personal data

- The job reads only each court's **public cause-list index**: which lists
  exist for which day, with the court's own PDF links. It never opens a list,
  never submits a party, counsel, AOR or case search, and never touches the
  CAPTCHA-protected searches (Supreme Court "search your case", Allahabad
  "cause list with status report", eCourts).
- A member's **court** is taken from their own profile (the courts they list,
  then the headline the invitation set, then bar council and state) through
  `groups.official.court_group_slug`, purely to decide which card to show them.
  Nothing about a member is sent anywhere. Generic entries ("High Court",
  "Family Court") match no court, so those members see no card.

## What members get

- **Daily page**, second card, "Your court": the court's name, the cause lists
  published for today and for the next listing day (each a link to the court's
  PDF), and buttons to the court's cause-list page, its website, eCourts (High
  Courts) and the court's official group. Courts whose index VidhiSangh does
  not read yet get the links only ("Today's cause list is on the court's website").
- **The court's official group**: one post by the official account the first
  time a day's lists are seen ("Cause list for tomorrow, Tuesday 17/11/2026",
  the list links, the court's page), so the group has something useful every
  working day.

## Public pages (17 November 2026)

`vidhisangh.com/courts/<slug>/cause-list/` (index at `/courts/`, `/sitemap-courts.xml`,
listed in robots.txt; nginx proxies `/courts/` to the API like `/judgments/`) shows
anyone the lists the court published for today and the next listing day, linked to
the court's own PDFs, the court's public details, a short explainer of the Supreme
Court's list types, a WhatsApp share and a join prompt (`utm_source=cause_lists`).
Rendered on request from `court_cause_lists`, cached 15 minutes, `dateModified` from
the last fetch. The point: "supreme court cause list today" is searched every working
day by exactly the advocates VidhiSangh is for, and the page is fresh twice a day.
Code `courts/public_pages.py`; test in `test_court_desk.py`.

## Courts read today

| Court | How | Lists |
|---|---|---|
| Supreme Court | `/cause-list/` "Cause lists at a glance" table (`fetch.parse_sci`): one row per listing day, fourteen columns in a fixed order; labels come from the column position, dates from the PDF path | advance; court-number-wise, judge-wise, chamber, single-judge, review & curative, registrar (main / supplementary); weekly |
| Allahabad High Court | each bench's cause-list form (`input1A.jsp`, `input1L.jsp`) with list type **Z, the combined cause list** (type D "daily" offers no dates) lists the dates a list exists for, as bare `<option value=dd-mm-yyyy>`; the link is the bench's index page (lists are court-wise pages) | "Combined cause list, Allahabad / Lucknow Bench" |

Every other High Court in `registry.COURTS` (one per official group, website
checked 16 Nov 2026) is link-only. Adding a court means a fetcher in
`fetch.py` returning `{date: [{label, url}]}` and the court's `fetcher` name in
the registry; nothing else changes. Candidates and the sites that were
unreachable on 16 Nov are in FUTURE_DELIVERABLES.

## The job

`vidhisangh-court-desk.timer`: **06:45 IST** (before the Daily brief) and
**18:00 IST** (the Supreme Court puts the next day's lists up in the evening),
Monday to Saturday, `Persistent=true` (idempotent). Each run:

1. fetches every court with a fetcher (a court whose site is down reports -1
   and the others still run; the unit does not fail);
2. records one row per court and day in `court_cause_lists` for today and later
   days; a row is updated when the court adds a list (a supplementary list in
   the evening) — `lists`, `fetched_at`;
3. posts rows with no `group_post_id` yet for **today and tomorrow** in the
   court's group and stamps the post id, so a day is announced once. Later
   days (the Supreme Court publishes advance lists two weeks ahead) are
   recorded for the card but never posted, and a stale day is never posted.

Dry run (nothing written; prints what each court's index says):

    sudo systemd-run --wait --pipe --collect --unit=court-desk-dry -p User=ubuntu \
      -p WorkingDirectory=/opt/vidhisangh/backend -p EnvironmentFile=/opt/vidhisangh/backend/.env \
      -E PYTHONPATH=/opt/vidhisangh/backend /opt/vidhisangh/backend/.venv/bin/python -m app.scripts.court_desk --dry-run

Journal lines: `court_desk_fetched` (court, days, changed), `court_desk_posted`,
`court_desk_fetch_failed` (court, error). Table: `court_cause_lists`.

## Not yet

- Fetchers for the other High Courts (their sites were slow or unreachable from
  the server on 16 Nov; see FUTURE_DELIVERABLES).
- Court notices and holiday lists ("court details" beyond the links).
- A member with no court on their profile could be asked once on the Daily page.

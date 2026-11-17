# VidhiSangh Daily — one brief a day for every member

Built 4 November 2026 after the owner asked for "something interesting to send each
user every day to increase their engagement". Code: `backend/app/modules/brief/`,
page `frontend/src/app/features/daily/`, job `app/scripts/daily_brief.py`,
units `infra/jobs/vidhisangh-daily-brief.{service,timer}`, migration `0089`.

## What a member gets

One page a day (`/app/daily`, also reachable from the home screen card and the
menu) with six items. The **lead** comes first and rotates by weekday, so the
morning message is never the same two days running:

| Day | Lead | Where it comes from |
|---|---|---|
| Monday | Section of the day (BNS / BNSS / BSA, old-law number) | the official account's post (`network/daily_sections.json`, 1,059 sections) |
| Tuesday | Supreme Court judgment of the day (AI headnote) | the official account's post |
| Wednesday | One quiz question | `brief/daily_quiz.json` (90 questions) |
| Thursday | On this day: a landmark decided on this date | `brief/daily_landmarks.json` (135 curated), else the corpus |
| Friday | The week in law (news) | the official account's news posts |
| Saturday | Your fraternity: who joined near you | `NetworkService.home` (counts, colleagues in my city, newest members) |
| Sunday | no message; the page shows *On this day* first | |

The other five items follow the lead in a fixed order (quiz, section, judgment,
on this day, news, fraternity). Since 16 November 2026 a **Your court** card
sits second, for members whose profile names a court: the cause lists the court
published for today and the next listing day, and links to the court's site and
group ([COURT_DESK.md](COURT_DESK.md)).

**Quiz.** One attempt per member and question. The answer and the explanation
are never in the page until the member has answered (`QuizRead.answer` is null
before that), then the page shows which option was right, the explanation, how
many members answered and how many were right, and a link to the section.
Questions walk a seeded shuffle of the bank from 4 November 2026 and wrap after
90 days; a past day's page shows that day's question.

**On this day.** Curated entries carry the case, date, citation, a one-line
holding and a `match` string used to find the corpus copy (±2 days, so the
registry's date may differ by a day) for the Read link. Every curated date was
checked against the production corpus before going live (132 of 144 matched
exactly; the 9 the corpus could not confirm were dropped; Rudul Sah and Kihoto
Hollohan were corrected to the registry's dates). Days with no curated entry
take the Supreme Court judgment decided on that month-day in any earlier year
that later judgments cite most: the sum of `judgment_aliases.support` (mined
citations; `case_citations` is empty in production), at least 3. The card shows
the AI summary when the judgment has one; otherwise only the citation count and
a Read link, because the registry's `headnote` column is a fragment of the text,
not a holding. A date with no judgment cited three times gets no card. The next
two weeks were checked on production: Pepsi Foods (1997), Prafulla Kumar Samal
(1978), Maru Ram (1980) and the curated Indira Gandhi, Kihoto Hollohan, Ajay
Hasia, Essar Steel and Indra Sawhney.

## The morning push

`vidhisangh-daily-brief.timer` fires at **07:30 IST, Monday to Saturday**
(`Persistent=false`: a missed run must not push at an odd hour). The job:

1. posts today's official items if not yet posted (`official.post_daily`, idempotent;
   the 08:00 official-posts timer then finds nothing to do), so the section and
   judgment exist before anyone is told about them;
2. pushes the lead's title and one line to every active member who has a
   registered phone (`push_devices`) and has not turned push off
   (`notification_preferences`, channel `push`), one row per member per day in
   `daily_brief_sends` claimed **before** sending (a rerun reports `already`);
   `unregistered` tokens are deleted. The job commits several times and re-applies
   the RLS bypass after each (`_commit`): the bypass is transaction-local, and the
   first live run (4 November, started by hand) pushed to nobody because the
   recipient query ran under RLS after the first commit and saw no users;
3. the push deep-links to `/app/daily?from=push&lead=<lead>`; opening the page
   that day stamps `opened_at` / `opened_via` on the row (a member who opens the
   page without a push gets a `viewed` row).

Dry run (nothing written or sent):

    sudo systemd-run --wait --pipe --collect --unit=brief-dry -p User=ubuntu \
      -p WorkingDirectory=/opt/vidhisangh/backend -p EnvironmentFile=/opt/vidhisangh/backend/.env \
      -E PYTHONPATH=/opt/vidhisangh/backend /opt/vidhisangh/backend/.venv/bin/python -m app.scripts.daily_brief --dry-run

Prints the day, the lead, whether it pushes today, how many members have the
app, and the message text.

## Measuring it

- `daily_brief_sends`: sent / failed / already per day (journal line
  `daily_brief`), and `opened_at` by `opened_via` (push vs app).
- `daily_quiz_answers`: answers and correct answers per question and per member.

A platform-admin view of these is not built yet (FUTURE_DELIVERABLES). For now:

    select for_date, lead, count(*) sent, count(opened_at) opened,
           count(*) filter (where opened_via = 'push') via_push
    from daily_brief_sends where status <> 'viewed' group by 1, 2 order by 1 desc;

## By email (17 November 2026)

Members **without the app** get the same brief by email every morning, in the
same job after the push and the WhatsApp message (`service.send_email_briefs`,
`brief/email.py` renders text and HTML, lead first, each item linked to its public
page and the quiz to the app; the member's court card is included when its lists
are known). Sent through the notifications SMTP (`VS_SMTP_*`, Brevo), which is a
separate account from the invitations' `VS_OUTREACH_SMTP_*`.

- **Preference** `daily_brief_email_prefs` (migration **0092**): no row means the
  default, on for members with no registered phone and off for members who get
  the push; `GET/PUT /notifications/daily-email` (`enabled`, `email_verified`,
  `has_app`, `chosen`); the switch is under Settings → Notifications. The generic
  Email channel switch pauses it too. Only verified addresses are mailed.
- **Unsubscribe**: every email carries `List-Unsubscribe` / one-click POST and a
  footer link to `/api/v1/brief/email/unsubscribe/<token>` (GET confirms, POST
  stops; the token rotates when the member switches it on again).
- **Log** `daily_brief_emails`: one row per member and day claimed before sending
  (sending | sent | failed, detail); opening the page from the email
  (`?from=email`) stamps `opened_at`. Journal line `daily_brief_email`.
- Dry run reports `email_recipients`.

## Not yet

- Admin statistics screen; a weekly "week in review" on Sunday if members want it.

## On WhatsApp (4 November 2026)

The owner asked for the brief on WhatsApp the day the push went live. Members
who say yes get the lead as the Meta MARKETING template **`vidhisangh_daily`**
(`en` and `hi`; header "VidhiSangh Daily", body with three parameters: first
name, the lead's title, one line; footer pointing to Settings; one URL button
to `/app/daily?from=whatsapp`) on their verified number, after the push, once a
day, Monday to Saturday.

- **Consent is its own topic.** The WhatsApp consent ledger
  (`whatsapp_updates_consents`) gained a `topic` column (migration **0090**):
  `updates` for product updates (the old rows) and `daily` for this. A yes to
  one never covers the other. `GET/PUT /notifications/whatsapp-daily` (same
  shape as `/whatsapp-updates`; `source` is `settings` or `daily`). The Daily
  page asks once ("Get VidhiSangh Daily on WhatsApp?", shown while unasked and
  the number is verified); Settings → Notifications has the switch
  (`vs-whatsapp-daily`).
- **Sending.** `service.send_whatsapp_briefs` runs in the same job after the
  push: recipients are active members with a verified number whose latest
  `daily` choice is yes, one per number; each send is claimed in
  `whatsapp_campaign_sends` (campaign `daily-brief-<date>`, template, language,
  basis `consent`, HMAC of the number) before the API call. A provider refusal
  is recorded as `failed` with the error code. The job reports the push and the
  WhatsApp step separately; either channel is skipped when unconfigured
  (`VS_WA_DAILY_TEMPLATE` empty disables WhatsApp). The unit carries the
  `wa_access_token` credential and `VS_WA_PHONE_NUMBER_ID`.
- **Template management.** `python -m app.scripts.whatsapp_template --submit
  vidhisangh_daily` creates the languages that do not exist yet; `--status`
  shows Meta's status and rejection reason; `--show` prints the definition.
  Run on the server inside a transient unit with the token credential (see
  DEPLOYMENT.md). Earlier templates were submitted by hand; this script holds
  the definition in the repo.
- Opening the page from the button is recorded as `opened_via = whatsapp`.

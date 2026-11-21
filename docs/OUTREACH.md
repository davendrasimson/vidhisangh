# Invitation emails (outreach)

Daily invitation emails to legal professionals who are not members yet.
Platform admin → **Outreach**. Built 16 Oct 2026 (migration `0067`).

## Conversion diagnosis and fixes (22 November 2026)

After 4,608 invitations: 588 opened (13%), 37 clicked (0.8%), 19 joined (0.4%); zero opens from
Yahoo and Rediff addresses (500+). Three leaks, each with a fix:

1. **Deliverability.** A real invitation sent to mail-tester scored **3.8/10**: `dmarc=fail`
   because the DKIM key lookup (`brevo1._domainkey.news.vidhisangh.com`, signed `d=news.vidhisangh.com
   s=brevo1`) failed at the receiver ("no servers could be reached"). The domain's only
   nameserver is BIND on the app server (ns1 and ns2 are the same host) with response rate
   limiting at 15/s per client, which drops the burst of SPF+DKIM+DMARC+CNAME lookups a receiver
   makes for one message. With `p=quarantine` on the subdomain that sends mail to spam. Done:
   rate limit raised to 60/s; `_dmarc.news` set to `p=none` until DNS is on a provider (back to
   quarantine then). The relay's shared IP was also on bl.spamcop.net that day (Brevo's problem;
   a dedicated IP is paid). **Recommended**: move the zone to Cloudflare or any provider with two
   real nameservers.
2. **The email.** Brand-first 90-character subject, four bullets before the button, signed
   "Team VidhiSangh". Now: subject under 60 characters naming the court ("Your colleagues at the
   Allahabad High Court are on VidhiSangh" once three invitees from that court joined, else "For
   advocates of the …: VidhiSangh, free"), the ask and the button in the first three lines, "already
   joined" line from 3 colleagues (was 5), signed Davendra Singh, alt text on images.
3. **The landing.** Half of those who clicked never finished the form (a WhatsApp-first screen,
   then name, email, role, password). The join link now opens the email form directly with name,
   email, court and city prefilled from the invitation (`GET /outreach/invite/<token>`, answers
   only while the invitation is open, `no-store`), a banner naming the court and how many
   colleagues joined, and funnel step `invite_prefilled`. Only the password is left to type.

Measure in the Outreach screen's funnel (sent → opened → clicked → joined) by the day the email
went out; the mail-tester check is repeatable from the server (send one `message_for` to a
test address through the job's SMTP credential).

## Rules the system enforces
- **One invitation per address, ever.** No follow-ups or reminders.
- **At most 100 a day** (`VS_OUTREACH_DAILY_LIMIT`, a ceiling the admin can only lower; 50 until the owner raised it on 31 Oct 2026), counted by India date; sent Monday–Saturday from about 10:30 IST, spaced 20–60 s apart (about 100 minutes for a full day) (`vidhisangh-outreach.timer`).
- **Starts paused.** Nothing goes out on the timer until the admin presses *Start scheduled sending* and the mail service is configured.
- **Court by court (owner, 2 Nov 2026; migration `0086`, `outreach_settings.focus`)**: the admin sets a **Focus** (a city or
  court name) on the Outreach screen; while it is set, the morning batch and *Send now* take only contacts whose city or court
  contains it, the screen shows how many are waiting in the focus, and when they run out nothing is sent until the focus is
  changed or cleared. The reasoning: a network needs density in one bar before breadth; a new member should find
  colleagues from their own court. First focus: **Prayagraj** (the Allahabad roll). Pace: the ceiling is now 500 a day
  (`VS_OUTREACH_DAILY_LIMIT`), the daily number stays 100 for week one; raise to 200, then 500, only if bounces stay under
  3 % and no complaints arrive (the sending domain is new). The job spaces messages 10–30 s apart.
  **`Random`** as the focus (11 Nov 2026) means every court, each contact picked at random from the whole queue
  (`ORDER BY random()`); an empty focus sends the oldest rows first. Any other text is matched against city and court,
  so a word that is not a place sends nothing (that is what happened on 11 Nov with "Random" before this mode existed).
- **Send now** (added 31 Oct 2026): the admin screen can send the rest of today's number straight away (`POST /platform-admin/outreach/send-now`), even while scheduled sending is paused. It runs inside the API process (`app/modules/outreach/runner.py`), 5–10 s apart, and the screen refreshes every 5 s until `sent_today` stops moving. The batch re-checks the day's budget before every message, so a run in two API workers, or alongside the morning timer, still stops at the daily number; each contact is committed as it is sent, so a worker restart mid-run leaves the rest queued and never re-sends. With nobody queued, or today's number already out, the button is disabled and the API answers 409 with the reason.
- **Skipped automatically:** existing members, anyone who unsubscribed or bounced before, duplicates, malformed addresses, rows without a source.
- **Unsubscribe**: the mail app's own button (RFC 8058 `List-Unsubscribe-Post`, no page) or the link in the footer (`/unsubscribe/:token`, one tap; not on page load, because mail scanners open links). Either puts a peppered hash of the address on `outreach_suppressions`, which outlives the contact row: the address can never be re-imported.
- **Hard bounce** (server refuses the address): suppressed the same way.
- **Joins** are recognised at sign-up by email and counted as *Joined*; a sign-up that arrives through the email's
  join link (`?invite=<token>`, carried by the register page as `invite_token`) is attributed to the invitation even
  with a different address.
- **Who reads it and who joins (2 Nov 2026, migration `0087`)**: `outreach_contacts` records the first
  `delivered_at`, `opened_at`, `clicked_at`, `complained_at`. The email's **join link** is
  `/api/v1/outreach/j/<token>` (records the click, 302 to `/auth/register?invite=<token>&utm_…`; unknown tokens still
  land on sign-up); a 1×1 **tracking image** `/api/v1/outreach/o/<token>.gif` records opens (Gmail and Apple fetch it
  for everyone, so opens read as "at least"); the relay's **webhook** `POST /api/v1/outreach/events/<secret>`
  (`VS_OUTREACH_WEBHOOK_SECRET`; 404 without it; Brevo does not sign webhooks, so the secret is the URL) records
  `delivered`, `opened`/`unique_opened`, `click`, `hard_bounce`/`invalid_email`/`blocked` (→ bounced + suppressed),
  `soft_bounce`/`deferred` (last_error), `spam` (→ complained, unsubscribed + suppressed) and `unsubscribed`. Every
  message carries `X-Mailin-Tag: invitation` so Brevo's own statistics can be filtered to the campaign. The Outreach
  screen shows the funnel sent → delivered → opened → clicked → joined (with "through the email's link"), the same by
  the day the email went out (last 14 days, a day's figures grow as it is read) and by court, and a *Read* column per
  contact; the CSV export carries the four new columns. Register the webhook with
  `python -m app.scripts.brevo_webhook --create` (needs a Brevo **v3 API key**, `BREVO_API_KEY`; the SMTP key does
  not work for the API).
- Each email names its **source** ("your professional email address is publicly listed in …"), the company, and the grievance officer.
- **Court-aware (1 Nov 2026)**: when a contact row has a `court`, the email adds "Advocates from the <court> are already on VidhiSangh" once five invitees from that court have joined (the exact number from 20), and "Your colleagues gather in the <court> group" linking the official group (`groups/official.court_group_slug`). At sign-up the invited member's profile starts with the list's city and "Advocate, <court>" as headline, so the home screen shows colleagues at once.

## Contacts list, removal flag, erasure (1 Nov 2026, migration `0084`)
- **Contacts** section on the admin screen: every contact with name, email, **mobile** (new CSV column
  `mobile`/`phone`, kept as 10 digits when it looks like an Indian mobile; shown, never used for sending),
  city · court, source, status and **Approached on** (`sent_at`). Search by name, email or mobile; filter by
  status; 50 a page, newest activity first; **CSV** export of the filtered list
  (`GET /platform-admin/outreach/contacts[.csv]?q=&status=&page=&size=`).
- **Asked to be removed**: when someone asks (by reply, call, grievance) to be taken off, the admin flags the
  row (`POST …/contacts/{id}/removal-request` with a note of how and when they asked). Status becomes
  `removal_requested`, the address goes on the suppression list like an unsubscribe, so it is never emailed
  and never re-importable; the flag, date and note show in the list and the counts.
- **Erase** (`DELETE …/contacts/{id}`): deletes the row (name, address, mobile, source) for good for a DPDP
  erasure request; the peppered suppression hash stays, so the address cannot come back through a later import.
- Statuses: waiting (`queued`), approached (`sent`), joined, unsubscribed, bounced, skipped, asked to be removed.

## DPDP note (owner's decision, 16 Oct 2026)
Addresses come from public directories collected by the owner. There is no
consent from recipients, so: keep each row's source accurate, send only to
professional (not personal) addresses, honour every unsubscribe and objection
at once (reply-to goes to `grievance@vidhisangh.com`), and stop if complaints
appear. The owner raised the ceiling from 50 to 100 a day on 31 Oct 2026; have counsel review before scaling further.

## Mail service (set up 16 Oct 2026)
Brevo, kept off the main domain's reputation: invitations come from
`invite@news.vidhisangh.com`; sign-up/verification mail stays on Titan.
- **DNS** (self-hosted BIND, `/etc/bind/db.vidhisangh.com`): `news` TXT `brevo-code:…` + `v=spf1 include:spf.brevo.com ~all`;
  DKIM CNAMEs `brevo1/brevo2._domainkey.news` → `b1/b2.news-vidhisangh-com.dkim.brevo.com` and, because the Brevo
  account also holds the main domain, `brevo1/brevo2._domainkey` → `b1/b2.vidhisangh-com.dkim.brevo.com` plus the
  root `brevo-code` TXT; `_dmarc.news` `p=quarantine; adkim=s` (the root DMARC is strict `p=reject`, so Brevo's DKIM
  must sign as news.vidhisangh.com). Branded links on **`links`** / `img.links` (CNAMEs to `*.brand.brevosend.com`):
  not `news`, which cannot be a CNAME while it carries the TXT records.
- **Server**: drop-ins `/etc/systemd/system/{vidhisangh-api,vidhisangh-outreach}.service.d/outreach.conf` set
  `VS_OUTREACH_SMTP_HOST=smtp-relay.brevo.com`, port 587, user `be802e001@smtp-brevo.com`, and load the SMTP key from
  `/etc/credstore.encrypted/vidhisangh.outreach_smtp` (systemd-creds). Changing them needs `systemctl restart`, not reload.
- **Brevo account**: the server IP `203.193.166.109` must be in *Security → Authorised IPs* (otherwise
  `525 5.7.1 Unauthorized IP address`); `invite@news.vidhisangh.com` must be an added sender.
- Rotate the SMTP key (it was pasted in a chat): new key in Brevo, then
  `printf %s NEWKEY | sudo systemd-creds encrypt --name=outreach_smtp - /etc/credstore.encrypted/vidhisangh.outreach_smtp`
  and restart both units.
- **Webhook (2 Nov 2026)**: the API drop-in also sets `VS_OUTREACH_WEBHOOK_SECRET` (a random 32+ character string;
  `openssl rand -hex 24`). Register Brevo's transactional webhook to
  `https://vidhisangh.com/api/v1/outreach/events/<secret>` either in Brevo → Transactional → Settings → Webhooks (events:
  delivered, hard bounce, soft bounce, blocked, spam, invalid, deferred, opened, click, unsubscribed) or with
  `BREVO_API_KEY=xkeysib-… python -m app.scripts.brevo_webhook --create` on the server. Open and click tracking in
  Brevo are optional: the email's own link and image record them without rewriting links.

## CSV format
Header row required: `email` (required), `name`, `city`, `court`, `source`.
`source` can instead be given once for the whole file in the upload form.
```
email,name,city,court,source
priya@lawchambers.in,Adv. Priya Sharma,Delhi,Delhi High Court,the Delhi High Court Bar Association directory
```

## Sources (first import, 31 Oct 2026)
Adding more lists? Read [OUTREACH_SOURCING.md](OUTREACH_SOURCING.md) first (rules, de-duplication, how to import, where to look next).

Addresses come only from official lists that publish professional contact details, each row
naming its list (the email prints it). Built with `scripts/outreach_build_contacts.py` from
`pdftotext -layout` output; role mailboxes (gov.in / nic.in, info@ …) and entries remarked
"Expired" are left out; one address per person; names the parser could not read cleanly are
blank (the email then says "Dear Colleague"). Imported on production: **3,046 contacts**, 0 invalid.

| List | Where | Rows |
|---|---|---|
| Supreme Court of India, *List of Advocates-on-Record as on 09.10.2026* (Record Room) | linked from https://www.sci.gov.in/advocate-on-record/ → `cdnbbsr.s3waas.gov.in/…/uploads/2026/10/2026100959.pdf` (543 pp.) | 2,319 |
| Delhi High Court, *nominated counsel for the Union of India* (Ministry of Law & Justice letter F.No. J-11017/19/2025-Judicial dated 11.09.2025; Lists A/B, standing and panel counsel) | https://delhihighcourt.nic.in/files/2026-08/nomcouncil/nominatedcounsel.pdf (380 pp.) | 711 (+102 already in the AOR list) |
| Supreme Court Bar Association, *life members* directory | https://scbaindia.org/lifemem.pdf (71 pp.) | 16 (older list; most addresses are in the AOR list) |

**Second import (1 Nov 2026, the owner asked for UP, Haryana, Punjab, Uttarakhand and Himachal with
mobiles): 21,351 contacts**, built with `scripts/outreach_build_contacts_states.py` (25 malformed addresses
dropped by the importer, 12 duplicates). Queue after it: 24,397 (about 8 months at 100 a day).

| List | Where | Rows |
|---|---|---|
| Allahabad High Court, *Roll of Advocates [Part-A] at Allahabad* (name, enrolment, address, mobile, email per advocate) | https://www.allahabadhighcourt.in/advocate/generateRollA.jsp?page=N, N = 1…317, 100 a page; crawled once, one page every 3 s | 21,194 (mobiles on ~99%) |
| Allahabad High Court, *advance notice to the State* directory of standing/special counsel, Lucknow Bench (June 2024) | https://allahabadhighcourt.in/event/event_19030_27-06-2024.pdf (104 pp.) | 150 after dropping office mailboxes and roll duplicates |
| Haryana State Legal Services Authority, *panel of advocates* (Panchkula) | https://cdnbbsr.s3waas.gov.in/s3e8ec28c8ef3e3c68482eef793edf3e50/uploads/2025/08/20250805223397979.pdf, linked from https://haryana.nalsa.gov.in/panel-of-advocates-retainers-and-plvs/ | 44 |

No official source with advocate **emails** was found for **Punjab, Uttarakhand or Himachal Pradesh** (1 Nov 2026):
P&H HC Legal Services Committee panels (2016 operative panel, 2025 pro-bono panel) and the Uttarakhand HC
mediator panel / DLSA brochures carry **mobiles only**; the Haryana DLSA/SDLSC panel PDF (~1,200 advocates) is
linked from the HSLSA page but 404s; slsa.uk.gov.in ("List of all panel lawyers") answered 503; the HP High
Court site (highcourt.hp.gov.in) is script-rendered and could not be read without a browser; the Bar Councils
of UP, Punjab & Haryana, Uttarakhand and HP publish no rolls with contact details; the Ministry's Union-of-India
panel-counsel profiles on legalaffairs.gov.in show a mobile but no email. The downloaded files and the counting
notes are in the session scratchpad only. Mobiles are stored for the admin's reference and are not used for
sending (WhatsApp outreach would need its own consent path and template approval).

**Third and fourth imports (1 Nov 2026, the owner asked for the rest of India and for corporate legal
professionals)**: 7,797 from the east and north-east, 13,390 from the west, centre and north (plus the Madhya
Pradesh High Court directory, below). Scripts: `scripts/outreach_build_contacts_east.py`,
`scripts/outreach_build_contacts_west.py`. Scanned (OCR) lists are only used where an address reads cleanly;
no address is ever "repaired".

| List | Where | Rows |
|---|---|---|
| Calcutta High Court, *Registered Advocates in CIS 1.0* (as on 04.01.2022, 23 weekly additions, and the Jalpaiguri master database up to 22.12.2022; mobiles masked) | `calcuttahighcourt.gov.in/Notice-Files/general-notice/<id>` ids 5371, 5463…6661, 7671, 7902 (found via `Notices/general-notice?page=26…62`) | 5,583 |
| Jharkhand High Court, *List of Advocates* as on 30.11.2024 | https://jharkhandhighcourt.nic.in/display_pdf/all_pdf/Reg_Advocates_List_as_on_30112024.pdf (246 pp.) | 1,995 |
| West Bengal SLSA panel lawyers, category A | https://cdnbbsr.s3waas.gov.in/s37f4bafbbbd694eeef3ab4c74cf22d8af/uploads/2025/10/202510102133873220.pdf | 106 |
| Gauhati High Court senior advocates (30.06.2022) and amicus curiae panel (03.12.2024, scanned: 3 clean) | https://ghconline.gov.in/SeniorAdvocatesDetails30062022.pdf, https://ghconline.gov.in/General/Notification-04-12-2024.pdf | 56 |
| Tripura HC Legal Services Committee empanelment, 27.06.2025 | https://hctlsc.tripura.gov.in/sites/default/files/data_notification/1174.pdf | 36 |
| Telangana High Court, Special Government Pleaders / Government Pleaders (2020; the AG office's shared mailbox dropped) | https://tshc.gov.in/documents/admin_2_2021_01_08_16_13_14.pdf | 24 |
| Maharashtra SLSA panel advocates and retainer lawyers, April 2026 (HCLSC Mumbai/Nagpur and every DLSA/TLSC) | https://cdnbbsr.s3waas.gov.in/s3cfdb78d53b9d4d154fc40a21f4794e71/uploads/2025/11/202607031858274862.pdf and …/20260703273438328.pdf, from https://maharashtra.nalsa.gov.in/list-of-panel-lawyers/ | 6,050 |
| High Court of J&K and Ladakh, *Advocate List as on August 2026* (the Bar Council roll; emails mostly from 2011 enrolments on) | https://jkhighcourt.nic.in/Advocate%20List%20as%20on%20AUGUST%202026.pdf (436 pp.) | 3,620 |
| J&K SLSA panel lawyers, June 2025 | https://cdnbbsr.s3waas.gov.in/s3b44f1f2aa18d557a3fecd5f8a0b0bb8c/uploads/2025/06/20250605903833802.pdf | 236 |
| Himachal Pradesh High Court, *Advocate On Record* directory (POST `advocate_search/adv_search_ajax.php`, one request per initial) | https://highcourt.hp.gov.in/advocate_search.html | 2,453 |
| Madhya Pradesh SLSA panel lawyers, June 2026 (rows wrap; name and email paired by proximity) | https://cdnbbsr.s3waas.gov.in/s370bfeb105a2a7019757b543303a2a79c/uploads/2026/06/20260603847617116.pdf | 818 |
| Gujarat High Court panel advocates for Government and public bodies as on 29.08.2026 (firms' office mailboxes dropped) | https://gujarathighcourt.nic.in/hccms/sites/default/files/judicailnotice/PANEL_ADVOCATES_LIST_AS_ON_29.08.2026.pdf | 147 |
| UT Chandigarh SLSA panel (Oct 2026) and P&H High Court arbitrator-advocate panels (2022, 2025) | https://cdnbbsr.s3waas.gov.in/s3a1e926947e6e1f41bee96af62f1cf811/uploads/2026/10/202610291954924640.pdf; https://www.highcourtchd.gov.in/sub_pages/common_upload/RulesOrders/ADRRules/ADVOCATES.pdf and …/Advocates.pdf | 73 |
| Ladakh Legal Services Authority panel | https://ladakh.nalsa.gov.in/list-of-panel-lawyers/ | 11 |
| Madhya Pradesh High Court advocates directory (`advocates-details/search?str=alpha&str1=<A–Z>&page=N`, `X-Requested-With: XMLHttpRequest`, 50 a page; the site's certificate chain is incomplete, so `curl -k --http1.1`) | https://mphc.gov.in/advocates-details | see PROJECT_STATUS (crawled 1 Nov 2026) |

**Fifth to seventh imports (1–2 Nov 2026)**: the Madhya Pradesh High Court directory (27,434 after the crawl of all
3,151 pages; a file is capped at 20,000 rows, so it went in two parts), **district court CIS exports** (25,921: the
eCourts district sites publish "Advocate details" exports with name, mobile and email under
`<district>.dcourts.gov.in/document-category/pleaders-and-bar-association/`; first batch Pune 14,215, Gurugram 2,115,
Rohtak 1,305, Hisar 1,076, Kangra 743, Bokaro 816, Shimla 621, Paschim Medinipur 664, Hazaribagh 459, Giridih 376 and
25 smaller districts of Haryana, HP, Jharkhand, WB, Punjab; the **sweep of all 750 district sites** that followed found lists with emails on 95 of them and added 10,660 more — Beed 1,961, Saran 781, Madhubani 764, Sonbhadra 732, Ayodhya 725, Kushinagar 630, Buxar 456, Bhadohi 425, Gaya 407, Wardha 281 and 85 others; about a fifth of the UP and Bihar rows carry no readable name and are greeted "Dear Colleague"), and
**8,577 from other official lists** (`scripts/outreach_build_contacts_professions.py`): the Department of Legal Affairs'
*Consolidated List of Panel Counsel for the Union of India* (April 2026, 556 pp., 4,759 parsed;
`legalaffairs.gov.in/cms/wp-json/wp/v2/central_documents?search=…` → `acf.pdf` → `/media/<id>`), its Law Officers and
DSGI lists (Aug 2026), Karnataka SLSA district panels (2,044), DSLSA panels (896), Assam SLSA panels (448), HP SLSA
trained mediators (361) and panels of legal practitioners (427), Rajasthan SLSA mediators (482; judicial officers left
out), the Odisha Law Department's law officers (105), IP India's trade marks agents as of 30.11.2020 (628; dated, expect
bounces), and law faculty from institutional directories: NLSIU (186), TNNLU (32), HPNLU (36), DNLU (28), DBRANLU (20),
ILI (8), NLUO (69), NUJS (56), NUSRL (31), NLU Tripura (9). Faculty rows carry no "Adv." and name the university as
their "court"; judicial academies were left out (serving judicial officers). Not done yet: GNLU (57) and NLU Jodhpur (55)
per-person pages, NALSAR (51), Kashmir Law (41). Found but unusable: notary lists (no contacts), patent agents register
(masked phones, no email), DIAC and High Court mediation panels (names only), prosecutors (mobiles only), BCI.

**No official source with advocate emails (1 Nov 2026)**: Tamil Nadu, Puducherry, Kerala, Karnataka, Andhra
Pradesh, Bihar, Odisha (HCLSC list is a poor scan), Sikkim, Meghalaya, Manipur, Mizoram, Nagaland, Arunachal,
Goa, Rajasthan, Chhattisgarh, Dadra & Nagar Haveli and Daman & Diu, besides Punjab, Uttarakhand and HP's bar
council. Mobiles-only lists exist for Bihar (BSLSA district panels), Rajasthan (RHCLSC pro bono), Chhattisgarh
(CGSLSA district panels, CG HC standing counsel), Gujarat (GSLSA panel, 2,006), Karnataka (none). Unreachable
from the server and worth a retry from a browser: bombayhighcourt.nic.in, slsa.tripura.gov.in master list,
mslsa.gov.in, cgslsa.gov.in, apslsa.ap.nic.in, sikkimslsa.nic.in, mslsa.gov.in (Meghalaya), slsa.uk.gov.in.

**Corporate legal professionals (1 Nov 2026): nothing imported.** Stock-exchange LODR disclosures (BSE
`CorpInfoNew` for 5,122 active scrips; NSE is a subset) give the Company Secretary / Compliance Officer's *name*
but the only email is the company's statutory investor-grievance mailbox (10 of 10 sampled), which is not a
professional contact address and should not be used. ICSI's member search is login-gated, MCA has no public
KMP emails, the Bar Councils have no corporate-counsel rolls (employed advocates suspend practice). Two
registers do carry individual emails but are not advocate lists: IBBI's insolvency professionals (~4,800,
`insolvency-professional/details?fieldid=<base64 id>`, mostly CAs/CMAs; ICSI-IIP members ≈ a quarter are company
secretaries; the email is published for insolvency-process contact) and SEBI's intermediary register (finance
professionals; JS pagination). Both left for the owner's decision.

Looked at and not usable (31 Oct): the Ministry's own panel-counsel PDFs on legalaffairs.gov.in (all 404 now),
the DHCBA empanelled-advocates list (no emails), Delhi High Court senior-advocate designations (no emails).
Next candidates when the queue runs low (~a month at 100/day): other High Courts' nominated-counsel
lists on their own sites, and bar associations that publish member directories with emails
(Gujarat HC Advocates Association, Kerala, Madras, Bombay, Allahabad — see bhattandjoshiassociates.com's
directory page for the links).

## Operations
- Dry run on the server: `python -m app.scripts.outreach_send --dry-run`
- Units: `infra/jobs/vidhisangh-outreach.{service,timer}`
- **"The morning job runs but sends 0"** — in order: (1) `outreach_contacts` is empty (nothing has been uploaded; the admin screen now says "Nobody is waiting to be invited"); (2) scheduled sending is paused; (3) today's number has already gone out (IST day). `journalctl -u vidhisangh-outreach` prints `outreach_batch sent=… skipped=… bounced=… failed=…` for each run; `failed=1` means the relay refused the connection and the run stopped (the contact's `last_error` has the reason).
- **"Send me a test" fails** — a failed relay call now comes back as 502 with the SMTP error text (before 31 Oct 2026 it was a 500: the route read a name field the token principal does not carry).
- **Bounce rate for the ramp rule**: until the Brevo webhook is registered, the screen's *bounced* counts only addresses refused at hand-over; Brevo → Transactional → Statistics (tag `invitation`) has the true hard-bounce figure. Once the webhook is on, the screen is the one to read.
- **Webhook check**: `python -m app.scripts.brevo_webhook` lists the account's transactional webhooks and says whether ours is registered; `journalctl -u vidhisangh-api | grep outreach_provider_event` shows events arriving.
- State on 31 Oct 2026: relay configured for the API and the job, scheduled sending **on**, limit 50, **no contacts ever imported**, so nothing has been sent yet.

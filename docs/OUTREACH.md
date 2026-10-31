# Invitation emails (outreach)

Daily invitation emails to legal professionals who are not members yet.
Platform admin → **Outreach**. Built 16 Oct 2026 (migration `0067`).

## Rules the system enforces
- **One invitation per address, ever.** No follow-ups or reminders.
- **At most 50 a day** (`VS_OUTREACH_DAILY_LIMIT`, a ceiling the admin can only lower), counted by India date; sent Monday–Saturday from about 10:30 IST, spaced 30–90 s apart (`vidhisangh-outreach.timer`).
- **Starts paused.** Nothing goes out on the timer until the admin presses *Start scheduled sending* and the mail service is configured.
- **Send now** (added 31 Oct 2026): the admin screen can send the rest of today's number straight away (`POST /platform-admin/outreach/send-now`), even while scheduled sending is paused. It runs inside the API process (`app/modules/outreach/runner.py`), 5–10 s apart, and the screen refreshes every 5 s until `sent_today` stops moving. The batch re-checks the day's budget before every message, so a run in two API workers, or alongside the morning timer, still stops at the daily number; each contact is committed as it is sent, so a worker restart mid-run leaves the rest queued and never re-sends. With nobody queued, or today's number already out, the button is disabled and the API answers 409 with the reason.
- **Skipped automatically:** existing members, anyone who unsubscribed or bounced before, duplicates, malformed addresses, rows without a source.
- **Unsubscribe**: the mail app's own button (RFC 8058 `List-Unsubscribe-Post`, no page) or the link in the footer (`/unsubscribe/:token`, one tap; not on page load, because mail scanners open links). Either puts a peppered hash of the address on `outreach_suppressions`, which outlives the contact row: the address can never be re-imported.
- **Hard bounce** (server refuses the address): suppressed the same way.
- **Joins** are recognised at sign-up by email and counted as *Joined*.
- Each email names its **source** ("your professional email address is publicly listed in …"), the company, and the grievance officer.

## DPDP note (owner's decision, 16 Oct 2026)
Addresses come from public directories collected by the owner. There is no
consent from recipients, so: keep each row's source accurate, send only to
professional (not personal) addresses, honour every unsubscribe and objection
at once (reply-to goes to `grievance@vidhisangh.com`), and stop if complaints
appear. Have counsel review before scaling beyond 50/day.

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

## CSV format
Header row required: `email` (required), `name`, `city`, `court`, `source`.
`source` can instead be given once for the whole file in the upload form.
```
email,name,city,court,source
priya@lawchambers.in,Adv. Priya Sharma,Delhi,Delhi High Court,the Delhi High Court Bar Association directory
```

## Operations
- Dry run on the server: `python -m app.scripts.outreach_send --dry-run`
- Units: `infra/jobs/vidhisangh-outreach.{service,timer}`
- **"The morning job runs but sends 0"** — in order: (1) `outreach_contacts` is empty (nothing has been uploaded; the admin screen now says "Nobody is waiting to be invited"); (2) scheduled sending is paused; (3) today's number has already gone out (IST day). `journalctl -u vidhisangh-outreach` prints `outreach_batch sent=… skipped=… bounced=… failed=…` for each run; `failed=1` means the relay refused the connection and the run stopped (the contact's `last_error` has the reason).
- **"Send me a test" fails** — a failed relay call now comes back as 502 with the SMTP error text (before 31 Oct 2026 it was a 500: the route read a name field the token principal does not carry).
- State on 31 Oct 2026: relay configured for the API and the job, scheduled sending **on**, limit 50, **no contacts ever imported**, so nothing has been sent yet.

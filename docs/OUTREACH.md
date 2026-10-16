# Invitation emails (outreach)

Daily invitation emails to legal professionals who are not members yet.
Platform admin → **Outreach**. Built 16 Oct 2026 (migration `0067`).

## Rules the system enforces
- **One invitation per address, ever.** No follow-ups or reminders.
- **At most 50 a day** (`VS_OUTREACH_DAILY_LIMIT`, a ceiling the admin can only lower), counted by India date; sent Monday–Saturday from about 10:30 IST, spaced 30–90 s apart (`vidhisangh-outreach.timer`).
- **Starts paused.** Nothing goes out until the admin presses *Start sending* and the mail service is configured.
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

## Connecting the mail service (owner, once)
Kept off the main domain so invitation complaints cannot hurt sign-up and
verification mail (Titan, `vidhisangh.com`).
1. Create a **Brevo** account (free: 300 emails/day) with `invite@news.vidhisangh.com` as the sender; add the domain `news.vidhisangh.com`.
2. Brevo shows DNS records (a TXT for ownership, DKIM `brevo1._domainkey` / `brevo2._domainkey` CNAMEs, and an SPF include). Send them to Claude: they go into `/etc/bind/db.vidhisangh.com` on the server (self-hosted DNS), plus `_dmarc.news` `v=DMARC1; p=quarantine; rua=mailto:grievance@vidhisangh.com`.
3. In Brevo → *SMTP & API*, create an SMTP key. On the server, as a systemd credential like the Titan password:
   ```
   VS_OUTREACH_SMTP_HOST=smtp-relay.brevo.com
   VS_OUTREACH_SMTP_PORT=587
   VS_OUTREACH_SMTP_USER=<Brevo SMTP login>
   VS_OUTREACH_SMTP_PASSWORD_FILE=/run/credentials/vidhisangh-outreach.service/outreach_smtp
   ```
4. Platform admin → Outreach → **Send me a test**, check it lands in the inbox (not spam), then **Start sending**.

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

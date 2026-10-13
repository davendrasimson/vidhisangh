# Google Play listing assets

Positioning (decided 11/10/2026): VidhiSangh is listed as a **free professional
network for India's legal fraternity**, with research, bare acts and practice
management as the reasons to stay. The listing text and screenshot order follow
that: network first, knowledge second, practice tools third.

| Play Console field | File | Spec met |
|---|---|---|
| App icon | `icon-512.png` | 512×512 PNG, no transparency |
| Feature graphic | `feature-graphic.png` | 1024×500 PNG |
| Phone screenshots (up to 8) | `phone-framed/` (see plan below) | 1080×1920, 9:16, PNG under 8 MB |
| 7-inch and 10-inch tablet screenshots (up to 8 each, optional) | `tablet-framed/` | 16:9 landscape, PNG under 8 MB |

The screens show fictional demo data (a demo firm and demo advocates, deleted
after capture) plus real public judgments, Acts and news from the product. Never
use a capture that shows a real user's name, photo, post or listing.

## Listing text

**App name** (25/30): VidhiSangh: Legal Network

**Short description** (79/80):
India's free professional network for advocates, judges, law students and firms

**Full description** (3171/4000):

VidhiSangh (विधि संघ — "the association of law") is a free professional network built for India's entire legal fraternity. One place to connect, learn, collaborate and grow, made for the way law is practised in India.

WHO IT IS FOR
• Advocates and Senior Advocates — from the Supreme Court and High Courts to district courts and tribunals
• Judicial officers and retired judges
• Legal researchers, law teachers and academics
• Law students and young advocates starting out at the Bar
• Court clerks, munshis and paralegals — the backbone of every chamber
• Law firms and chambers of every size
• In-house counsel and corporate legal teams
• Government law officers, arbitrators and mediators

BUILD YOUR PROFESSIONAL IDENTITY
• A profile made for law: enrolment, Bar Council, courts of practice, practice areas, education, publications, memberships and achievements
• Get verified so colleagues know they are dealing with a genuine professional
• Choose who sees your details: everyone, connections only, or no one

CONNECT WITH THE FRATERNITY
• Discover advocates, firms and legal professionals across courts and cities
• Send connection requests, follow seniors and peers, and grow a trusted network across India
• Share your digital visiting card with a QR code

SHARE, DISCUSS AND LEARN
• Post updates, judgments, articles and practical insights
• React, comment, repost and save posts; join conversations with hashtags such as #BNSS, #Arbitration or #ServiceLaw
• See what the legal community is talking about this week

COMMUNITIES
• Join or create communities by practice area, court, bar association, city or law school
• Firm pages and moderated private groups for chambers, alumni and teams

MESSAGING
• Private one-to-one and group chats with fellow professionals, in real time

REFERRALS, LOCAL COUNSEL AND OPPORTUNITIES
• Need counsel in another city or court? Post a request and receive responses from professionals there
• Find referrals, local counsel, experts, researchers, arbitrators, jobs and internships

KNOWLEDGE AT YOUR FINGERTIPS
• Search millions of Supreme Court and High Court judgments and orders, with parties, counsel, bench and case history
• Read BNS, BNSS, BSA and other central Acts as clear, searchable text, available offline
• Legal news, notifications and court updates linked to their official sources

TOOLS FOR YOUR PRACTICE (OPTIONAL)
When you need them, the same app runs your practice:
• Matters with hearings, team, documents and fee arrangements
• Calendar of hearings, deadlines and limitation dates
• Clients with KYC, consent and GST/TDS details
• Drafting of court and office formats in English, Hindi and Punjabi, with e-signatures
• Time entries and GST invoices

PRIVACY AND TRUST
Your data is encrypted in transit and at rest and handled under the Digital Personal Data Protection Act, 2023. Firm data stays separate for each organisation. You can download your data or delete your account at any time from Settings.

Joining VidhiSangh and networking with the legal fraternity is free.

Join the network built for India's legal professionals. विधि का संघ, आपके साथ.

Privacy policy: https://vidhisangh.com/privacy

## Screenshots (captured 11/10/2026)

Google shows at most 8 phone screenshots, and the first 3 decide most installs,
so they carry the network story. All 18 screens are in `phone/` (plain) and
`phone-framed/` (with caption). Upload the 8 marked **Play** from
`phone-framed/`, in that order. The rest are spares for the website, social
posts and a later tablet set. The 8 October practice-first set is kept in
`archive-2026-10-08/`.

| File | Segment | Caption | Play |
|---|---|---|---|
| 01-feed | Network | Your legal fraternity, in one feed | **1** |
| 02-profile | Network | Your professional identity, verified | **2** |
| 03-people | Network | Connect with advocates across India | **3** |
| 04-groups | Network | Communities for every court and practice | **4** |
| 05-messages | Network | Talk shop, in real time | |
| 06-marketplace | Network | Find local counsel and referrals | |
| 07-research | Knowledge | 5.9 million judgments, one search | **5** |
| 08-judgment | Knowledge | Read every order in context | |
| 09-bareact | Knowledge | BNS, BNSS, BSA — clear and offline | **6** |
| 10-news | Knowledge | Legal news that matters to you | |
| 11-dashboard | Practice | Your practice at a glance | |
| 12-matters | Practice | Every case, every court | **7** |
| 13-fees | Practice | Fees tracked milestone by milestone | |
| 14-calendar | Practice | Never miss a hearing | |
| 15-clients | Practice | Clients, KYC and GST in one place | |
| 16-documents | Practice | Draft in English, Hindi and Punjabi | |
| 17-billing | Practice | GST invoices in a tap | **8** |
| 18-matter | Practice | The whole case on one page | |

Captured on a 1080×1920 Android emulator from the release UI, against
production, signed in as a fictional firm ("Kulshreshtha & Associates") with
five fictional advocates, clients and matters. All of it was deleted after
capture. On the People screen, everyone other than the demo advocates was
hidden before capture so no real user appears. Research, Bare Acts and News
show real public content.

Timesheets were not captured. The timesheet table is too cramped at phone
width; capture it for a tablet set once that screen has a phone layout.

## Regenerating

Boot the emulator at 1080×1920 (see `docs/MOBILE.md`), enable status-bar demo
mode, sign in to a demo organisation, capture with `adb exec-out screencap -p`,
then frame with headless Chrome using the brand gradient (#173b7a → #215dcc →
#4934b8), Source Serif 4 headings and Inter captions in #f4c86a.

# App Store listing assets (iOS)

Captured 21 November 2026 with `frontend/scripts/app-store-screenshots.mjs` from the live
site, signed in as the reviewer account (a fictional advocate, "Priya Kulshreshtha", with the
guided sample workspace). The sample-data banner and every card that lists real members are
hidden during capture; Research, Bare Acts, News and the court's cause lists show public content.

| Folder | Size | App Store slot |
|---|---|---|
| `iphone-69/` | 1320×2868 | iPhone 6.9" (also covers the smaller iPhones) |
| `ipad-13/` | 2064×2752 | iPad 13" |

Order: 01 Daily (court card + question), 02 Home, 03 Groups, 04 Legal research, 05 Bare Act
reader, 06 Matters, 07 Calendar, 08 Legal news.

Uploaded to App Store Connect through the API (`~/.config/vidhisangh-ios/upload_screenshots.py`
on the owner's machine), together with the listing text (adapted from the Play listing in
`../google-play/README.md`), subtitle "India's legal fraternity", categories Social Networking /
Business, age rating 4+, price free in every territory, build 1 of 1.0.6 and the App Review
demo account. Regenerate: `REVIEW_PASSWORD=… node scripts/app-store-screenshots.mjs` from
`frontend/` (sign-in is rate-limited; the script waits between the two sets).

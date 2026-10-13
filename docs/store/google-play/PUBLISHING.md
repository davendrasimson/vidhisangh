# Publishing VidhiSangh on Google Play — step by step

Everything Google asks for is prepared below. The steps marked **(you)** need your
Google account, payment or identity and cannot be done for you. Google changes the
Play Console wording from time to time; the steps are the same even if a label moves.

## What is ready

| Item | Where |
|---|---|
| Signed release bundle (upload this) | `~/vidhisangh-release/vidhisangh-1.0.0-release.aab` (built 11/10/2026, version 1.0.0, versionCode 1, target SDK 36) |
| Same build as an installable APK (for testers' phones) | `~/vidhisangh-release/vidhisangh-1.0.0-release.apk` |
| App icon 512×512, feature graphic 1024×500, 8 phone screenshots | `docs/store/google-play/` (see README.md there) |
| Short and full description | `docs/store/google-play/README.md` |
| Privacy policy (public) | https://vidhisangh.com/privacy |
| Account deletion: in-app | Settings → Privacy & data → Delete my account |
| Account deletion: web link | https://vidhisangh.com/privacy (section "Erasure" explains the steps) |
| Upload key | `~/.vidhisangh-signing/android/` — back it up; SHA-256 `BD:85:F0:FA:35:6D:22:94:24:FD:06:C2:A0:3B:23:58:12:86:28:93:3E:53:D9:A8:F8:37:3C:6A:44:ED:00:4F` |

## Step 1 — Create the developer account (you)

1. Go to https://play.google.com/console and sign in with the Google account that should own the app long term (ideally a company account, not a personal Gmail you may lose).
2. Choose the account type:
   - **Organisation** (recommended for a company): needs a D-U-N-S number for the company, a company website and email. No mandatory closed test before going public.
   - **Personal**: faster to open, but Google requires a closed test with at least 12 testers who stay opted in for 14 days in a row before you can publish to everyone.
3. Pay the one-time registration fee (USD 25) and complete identity verification (government ID, phone and email checks). Verification can take a few days.

## Step 2 — Create the app (you)

Play Console → **Create app**:
- App name: `VidhiSangh`
- Default language: English (India) – en-IN
- App or game: App · Free or paid: Free
- Tick the Developer Programme Policies and US export laws declarations.

## Step 3 — App content declarations

Play Console → **Policy and programmes → App content**. Answers to use:

| Declaration | Answer |
|---|---|
| Privacy policy | `https://vidhisangh.com/privacy` |
| App access | "All or some functionality is restricted". Give a reviewer login (see Step 6). Instructions: "Sign in with the email and password below. The account has sample matters, clients and documents." |
| Ads | No, the app does not contain ads |
| Content rating | In the questionnaire choose the category **"All other app types"**. Answer **No** to violence, sexual content, profanity, drugs and gambling. Answer **Yes** to "users can interact or exchange information" (users can message each other) and **No** to "shares the user's current location". Expected rating: Everyone / 3+ with the "Users interact" notice. |
| Target audience | 18 and over only. Not designed for children. |
| News app | No |
| COVID-19 contact tracing/status | No |
| Data safety | See Step 4 |
| Government app | No |
| Financial features | "My app doesn't provide any financial features" (billing and invoices are a practice-management tool for the firm, not a consumer financial service) |
| Health apps | No health features |
| Account deletion | In-app path: Settings → Privacy & data → Delete my account. Web link: `https://vidhisangh.com/privacy` |

## Step 4 — Data safety form

**Overview questions**
- Does the app collect or share user data? **Yes**
- Is all data encrypted in transit? **Yes** (HTTPS only; the app refuses plain HTTP)
- Do you provide a way for users to request deletion? **Yes**

**Data types collected** (mark each as *Collected*, **not** Shared — service providers that process data for you, such as the email/WhatsApp code sender, do not count as sharing):

| Data type | Collected | Purpose | Optional? |
|---|---|---|---|
| Personal info → Name | Yes | Account management, App functionality | Required |
| Personal info → Email address | Yes | Account management, App functionality | Required (or phone) |
| Personal info → Phone number | Yes | Account management (WhatsApp sign-in code), App functionality | Optional |
| Personal info → Address | Yes | App functionality (client records) | Optional |
| Personal info → Other info | Yes | App functionality (client KYC details such as PAN, entered by the firm) | Optional |
| Financial info → Other financial info | Yes | App functionality (invoices, fee arrangements, client GST/TDS details) | Optional |
| Messages → Other in-app messages | Yes | App functionality (messages between users) | Optional |
| Files and docs | Yes | App functionality (documents the user uploads or drafts) | Optional |
| App activity → Other user-generated content | Yes | App functionality (matters, notes, research workspace) | Optional |

Do **not** tick: location, contacts, photos/videos (files are chosen by the user and counted under Files and docs), audio, health, web browsing, device IDs, crash logs or diagnostics (the app contains no analytics or crash-reporting SDK).

For every type: data is **processed ephemerally? No**; **collected, not shared**.

## Step 5 — Store listing (Grow → Store presence → Main store listing)

- App name: `VidhiSangh: Legal Network` (the name can be changed later; the package name cannot)
- Short description and full description: copy from `docs/store/google-play/README.md`
- App icon: `icon-512.png` · Feature graphic: `feature-graphic.png`
- Phone screenshots, from `phone-framed/` in this order: `01-feed`, `02-profile`, `03-people`, `04-groups`, `07-research`, `09-bareact`, `12-matters`, `17-billing` (the README lists the other 10 spares)
- Category: **Business** · Tags: professional networking, legal, practice management
- Contact details: email (use a monitored mailbox such as a Titan support address on vidhisangh.com), website `https://vidhisangh.com`
- Countries: India (add others later if wanted)

## Step 6 — Reviewer login

Created 12/10/2026 on production: organisation "VidhiSangh Play Review", user `play-review@vidhisangh.com` (email verified, sample matters, clients and documents, hidden from the People directory). The password was handed to the owner directly and is not stored in this repo. Paste both into **App access**. Keep this account while the app is listed; do not delete it in test clean-ups.

## Step 7 — Release

1. **Testing → Internal testing → Create new release** (fastest, no review queue). Upload `vidhisangh-1.0.0-release.aab`.
   - First upload: accept **Play App Signing** (Google keeps the final signing key; your file in `~/.vidhisangh-signing` stays the upload key, and Google can reset it if it is ever lost).
   - Release name: `1.0.0`. Release notes: "First release of VidhiSangh for Android."
   - Add testers by email list, roll out, and share the opt-in link. Install from Play on a real phone and check sign-in, matters, a document download and the act reader.
2. **Personal accounts only:** create a **Closed testing** track, add at least 12 testers, and keep them opted in for 14 days. Then apply for production access from the Dashboard.
3. **Production → Create new release**, promote the same build (or upload it), roll out to 100% (or a staged percentage) and **Send for review**. First reviews usually take a few days.

## Later updates

For every new upload, raise `versionCode` (2, 3, …) and usually `versionName` in `frontend/android/app/build.gradle`, then:

```
cd frontend && npm run build:mobile
cd android
export JAVA_HOME=~/.local/jdk/jdk-21.0.12.1+1 ANDROID_HOME=~/Android/Sdk
export VIDHISANGH_KEYSTORE_PROPERTIES=~/.vidhisangh-signing/android/keystore.properties
./gradlew bundleRelease          # app/build/outputs/bundle/release/app-release.aab
```

The app shows live data from vidhisangh.com, so most changes (new headnotes, data, server features) reach app users without a store update. A new upload is needed only when the bundled screens change.

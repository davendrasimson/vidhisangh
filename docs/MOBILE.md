# VidhiSangh Android and iOS apps

The apps are the Angular frontend packaged with **Capacitor 8**. One codebase
serves the website and both apps. The app bundles its own copy of the frontend,
including the bare-act PDFs, so it opens without a network. It talks to the live
API at `https://vidhisangh.com/api/v1`.

| | |
|---|---|
| App ID (both stores) | `com.vidhisangh.app`. Permanent: changing it creates a different app. |
| Display name | VidhiSangh |
| Version | Android `versionCode 1` / `versionName 1.0.0`; iOS `MARKETING_VERSION 1.0.0` / build `1` |
| Android | min SDK 24 (Android 7), target and compile SDK 36 (Android 16) |
| iOS | iOS 15+, iPhone and iPad, Swift Package Manager (no CocoaPods) |
| Native plugins | App (back button), Filesystem + Share (downloads), Splash Screen |

## How the app differs from the website

| Concern | Website | App |
|---|---|---|
| Page origin | `https://vidhisangh.com` | `https://localhost` (Android), `capacitor://localhost` (iOS) |
| API calls | same-origin `fetch` | `CapacitorHttp` patches `fetch`/XHR onto the native HTTP stack |
| Refresh cookie (`vs_refresh`, HttpOnly, SameSite=Strict) | browser cookie jar | OS cookie store via native HTTP. A WebView request from localhost would be cross-site and never carry it |
| Service worker | on | off: assets ship inside the app |
| File downloads | hidden `<a download>` | `core/platform/save-file.ts` writes to the app cache and opens the system share sheet (Open, Save to Files, Drive, WhatsApp, Print) |
| Links for other people (pay, portal, judgment links) | `location.origin` | `publicOrigin()` returns `https://vidhisangh.com` |
| Act PDFs | shown in a frame | handed to the phone's PDF viewer; Android WebView cannot render PDFs |
| Passkeys and SSO buttons | shown | hidden: both are bound to the vidhisangh.com origin (see open items) |
| Android back button | n/a | walks the app's history; exits on the dashboard or login screen |
| vidhisangh.com links (from 1.0.6) | open the page | `/app/…`, `/join/…`, `/auth/verify-email/…`, `/auth/reset/…` open in the app (App Links, `core/platform/app-links.ts`); everything else stays in the browser |
| Store rating (from 1.0.6) | n/a | Play's rating sheet now and then (`core/platform/review-prompt.ts`, native `InAppReviewPlugin.java`) |

Use the canonical host **vidhisangh.com**, never www. The www host only proxies
plain API calls and has no WebSocket route, so real-time updates fail there.

Rules for new frontend code, enforced by `frontend/tests/mobile-app.test.mjs`:

- Save files with `saveBlob()` from `@core/platform/save-file`, never an anchor with `download`.
- Build shareable links with `publicOrigin()` from `@core/platform/platform`, never `location.origin`.
- Use `isNativeApp()` for anything that must behave differently in the app.

## Files

| Path | What it is |
|---|---|
| `frontend/capacitor.config.ts` | App ID, web folder, native HTTP on, bridge logging off, splash, safe-area handling |
| `frontend/src/environments/environment.mobile.ts` | Absolute API and public URLs for the app build |
| `angular.json` → `configurations.mobile` | Swaps in the mobile environment, no service worker, output to `dist-mobile/` so an app build can never be deployed to the website |
| `frontend/src/app/core/platform/` | `platform.ts`, `save-file.ts`, `native-shell.ts` (safe area, back button, splash) |
| `frontend/android/`, `frontend/ios/` | Native projects. Commit them; `npx cap sync` regenerates only the copied web assets and plugin lists |
| `frontend/resources/` | Icon and splash SVG sources plus `generate.sh`, which renders every platform size |

## Build: Android (Linux, macOS or Windows)

Needs JDK 21 with `javac` and the Android SDK (platform 36, build-tools 36).
On the Linux dev box these live in `~/.local/jdk/jdk-21*` and `~/Android/Sdk`.

```
cd frontend
export JAVA_HOME=~/.local/jdk/jdk-21.0.12.1+1 ANDROID_HOME=~/Android/Sdk
npm run build:mobile                          # ng build -c production,mobile && cap sync
cd android && ./gradlew assembleDebug         # app/build/outputs/apk/debug/app-debug.apk
```

Release builds are signed with the **upload key**, kept outside git:

```
export VIDHISANGH_KEYSTORE_PROPERTIES=~/.vidhisangh-signing/android/keystore.properties
cd frontend/android && ./gradlew bundleRelease assembleRelease
# app/build/outputs/bundle/release/app-release.aab   -> upload to Google Play
# app/build/outputs/apk/release/app-release.apk      -> direct install / testers
```

The properties file holds `storeFile`, `storePassword`, `keyAlias`, `keyPassword`.
Without it, release builds come out unsigned and debug builds are unaffected.
Upload key certificate SHA-256 (Play app signing key `2E:16:…:43:99` is in `public/.well-known/assetlinks.json` too, added 22 Oct 2026):
`BD:85:F0:FA:35:6D:22:94:24:FD:06:C2:A0:3B:23:58:12:86:28:93:3E:53:D9:A8:F8:37:3C:6A:44:ED:00:4F`.
**Back up the keystore and its properties file off this laptop.** With Play App
Signing turned on, Google holds the real app signing key and a lost upload key can
be reset through Play support. Without it, a lost key means no further updates.

## Build: iOS (macOS with Xcode only)

iOS apps can only be compiled and signed on a Mac. The Xcode project is ready.

```
cd frontend && npm ci && npm run build:mobile
npx cap open ios                              # opens ios/App/App.xcodeproj
```

In Xcode: select the **App** target, set **Signing & Capabilities → Team** to the
VidhiSangh Apple Developer account, then **Product → Archive → Distribute App →
App Store Connect**. Swift packages resolve on first open. Before the first
upload, check **Product → Archive → Generate Privacy Report** and declare the
data the app handles in App Store Connect's privacy section.

Already set in `ios/App/App/Info.plist`: display name, `ITSAppUsesNonExemptEncryption = false`
(standard HTTPS only), and camera and photo-library usage texts. Those texts are
required because iOS offers "Take Photo" in every file picker, and the app
crashes without them.

## Icons and splash screens

Edit the SVGs in `frontend/resources/` and run `frontend/resources/generate.sh`.
It needs `google-chrome` and ImageMagick. It writes the iOS 1024 px icon and
splash, Android legacy, round and adaptive icon layers for every density (the
foreground also serves as the Android 13+ themed icon), and Android splash images.

## Live screen updates (since 1.0.3, 14 October 2026)

Screen, text and style changes reach installed apps without a store update.
The app ships its screens built in; on each launch it reads
`https://vidhisangh.com/app-updates/latest`, downloads only the files that
changed (hash-checked, identical files copied from the built-in screens) and
switches when the user next leaves and reopens the app. Code:
`src/app/core/platform/live-update.ts` with the `@capgo/capacitor-updater`
plugin in manual mode. No Capgo cloud service is used: update checks, stats and
channel calls are switched off in `capacitor.config.ts` (a test enforces this).

To publish (from `frontend/`, after the website deploy so both match):

```
npm run publish:app-update                    # Android
npm run publish:app-update -- --platform ios  # iOS
npm run publish:app-update -- --dry-run       # build and count files only
```

- A release targets exactly one native build (Android `versionCode`, iOS
  `CURRENT_PROJECT_VERSION`) read from the project, so screens never run on
  native code they were not built with. After a store update, publish again for
  the new build.
- **While a store update is rolling out or in review, phones on the previous
  build get nothing new** unless you also publish to it:
  `npm run publish:app-update -- --also 5=1.0.4` (repeatable). Safe only when
  every plugin added since that build is optional in the JS (push.ts,
  review-prompt.ts check for it). Missed on 21–22 Oct 2026: the owner's phone,
  still on 1.0.4 (build 5), received none of six updates published for build 6.
  Which builds are still checking: `grep app-updates/latest` in the nginx log
  (the user agent shows the phone, not the build; the download pattern does).
- A store update discards downloaded screens (`resetWhenUpdate`).
- **A fresh download has status `pending`**, not `success` (that comes only after
  it has started once). From 20 to 22 Oct 2026 the app only switched to `success`
  bundles, so every phone on 1.0.5, and 1.0.4 after its 21 Oct update, downloaded
  updates and never used them; only a store update (1.0.6) could fix it. Verified
  on the emulator 22 Oct: launch 1 downloads (`pending`), launch 2 switches
  (`success`). `usableBundle()` + a unit test guard it.
- **Account menu → Update app** (1.0.6+): checks now, downloads, and switches at
  once; the menu also shows "App 1.0.6 · screens dd/mm/yyyy hh:mm".
- If new screens fail to start, `notifyAppReady()` is never called and the
  plugin returns to the previous screens; that version is never retried. A
  failed download is retried on the next launch.
- Still needs a store update: a new or upgraded Capacitor plugin, permissions,
  icons, splash, or anything in `android/` or `ios/`.
- Server: `/opt/vidhisangh/frontend/dist/vidhisangh/browser/app-updates/`
  (`latest` plus `files/<sha256>`; content-addressed, never deleted by the dist
  rsync). Files must be world-readable for nginx; the script sets 755/644.
- To withdraw a release, delete its entry from `latest` (the app then keeps the
  screens it has; the next published release replaces them).
- The plugin pulls in WorkManager (permissions WAKE_LOCK, ACCESS_NETWORK_STATE,
  RECEIVE_BOOT_COMPLETED, FOREGROUND_SERVICE; no foreground-service type, so no
  Play declaration). R8 removed WorkManager's database constructor and the app
  crashed on start; `proguard-rules.pro` keeps it.
- Verified 14/10/2026 on the emulator with a throwaway build 999: delta download
  of 6 changed files in ~3 s, switched after Home → reopen, kept after a cold
  start; the test release was then removed from `latest`.

## Verification done (4 October 2026)

On an Android 16 emulator, against production, with a throwaway organisation
that was deleted afterwards:

- Debug build: sign-in through the real login form, session restored after the app was killed and relaunched, no tokens in `localStorage`, no service worker, clients, matters, documents, research and calendar screens, back button, real-time WebSocket connected, zero console or CSP errors.
- A PDF uploaded from inside the app (native multipart) and downloaded with the app's Download button came back byte-identical (MD5 match). Downloads and the act-reader PDF open the system share sheet.
- Signed release APK: sign-in by typing, session survives a restart, only the `INTERNET` permission, no credentials in the device log.
- Not verified: the iOS build. It needs a Mac.

## Before publishing

Google Play (one-time USD 25 developer account):
1. Create the app as `com.vidhisangh.app`, opt in to Play App Signing, upload `app-release.aab` to Internal testing first.
0. Step-by-step Play Console guide with ready-to-paste answers: [store/google-play/PUBLISHING.md](store/google-play/PUBLISHING.md).
2. Store listing: screenshots, feature graphic, icon and draft text are ready in [store/google-play/](store/google-play/README.md); privacy policy URL `https://vidhisangh.com/privacy`.
3. Data safety form: account data (name, email, phone), client and matter records the user enters, uploaded documents. All encrypted in transit; users can request deletion.
4. Account deletion: Play requires an in-app path and a web URL. The privacy settings page covers data export and rights requests; confirm a self-service "delete my account" request is reachable from it before submitting.
5. Reviewer access: give a demo login in the Play Console ("App access"). Use a dedicated reviewer account, not a real firm's data.

Apple App Store (USD 99 per year Apple Developer Program):
1. Register the bundle ID `com.vidhisangh.app` and create the app in App Store Connect.
2. Same privacy URL, privacy labels, demo account and account-deletion rule (guideline 5.1.1(v)).
3. Guideline 4.2 rejects apps that are "just a website". This app ships its own interface, offline bare acts and native file sharing; adding push notifications and biometric unlock (open items) further strengthens the case.

## App Links and the rating sheet (1.0.6)

- The manifest claims `https://vidhisangh.com` with the four path prefixes in
  `app-links.ts` (a unit test keeps the two in step). Android verifies them
  against `https://vidhisangh.com/.well-known/assetlinks.json`
  (`frontend/public/.well-known/`), which must list the SHA-256 of **every key
  that signs installed apps**: the upload key (listed) and Play's app signing key
  (Play Console → App integrity; add it). Unverified, links simply open in the
  browser. Check on a phone with `adb shell pm get-app-links com.vidhisangh.app`.
- Emulator test without verification: `adb shell pm set-app-links-user-selection
  --user 0 --package com.vidhisangh.app true vidhisangh.com`, then
  `adb shell am start -a android.intent.action.VIEW -d https://vidhisangh.com/join/CODE`.
- The rating plugin is app-local (not an npm package: the community plugin's
  Gradle file is rejected by AGP 9). Live screen updates reach older builds, so
  the JS checks `Capacitor.isPluginAvailable('InAppReview')` first.

## Open items

Recorded in [FUTURE_DELIVERABLES.md](FUTURE_DELIVERABLES.md) under Mobile.

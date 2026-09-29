# Product help

Read the [user guide](user-guide.md) or open **Help & feature tour** in the application.

- **Help** opens guidance for the current page, including record details, settings, timesheets and Bare Acts views.
- The **light bulb** opens a contextual tip. Dialogs preserve unfinished forms, trap keyboard focus, close with Escape and return focus to their trigger.
- The help landing page lists prominent features, searchable articles and a replayable overview tour. Authenticated tours omit permission-restricted features the user cannot access. Articles remain discoverable and explain that availability varies.
- Public sign-in, signing, KYC, payment and portal pages have their own help. Help links carry only an article ID, never a private invitation token or record ID.
- On narrow screens, help and tips remain in the top bar. Support is available in the account menu; appearance controls remain in Settings.

## Maintaining help

Edit `frontend/src/app/features/help/help-content.ts` when workflows change. Each routable page needs a title, summary, practical steps and a contextual tip. Keep permissions aligned with navigation and mark prominent features with `featured: true`.

Regenerate the printable guide with `cd frontend && npm run docs:help`. Do not manually edit the generated guide.

## Verification

Use Node 22.18+ or Node 24 for the TypeScript-aware content tests and generator.

```sh
cd frontend
npm ci
npm test
npm run test:e2e
```

Install Chromium once with `npx playwright install chromium`, or set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to an existing Chrome/Chromium binary. Browser tests serve the production build locally and intercept APIs with deterministic fixtures. They verify UI behavior, not live provider integration.

See [rollout validation](../ROLLOUT_VALIDATION.md) for the broader application results and remaining release gates.

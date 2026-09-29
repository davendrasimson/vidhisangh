import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  workers: 2,
  timeout: 45_000,
  use: {
    baseURL: process.env['PLAYWRIGHT_BASE_URL'] ?? 'http://127.0.0.1:4301',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    launchOptions: process.env['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH']
      ? { executablePath: process.env['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] } : {},
  },
  webServer: process.env['PLAYWRIGHT_BASE_URL'] ? undefined : {
    command: 'node tests/serve-app.mjs', url: 'http://127.0.0.1:4301/help', reuseExistingServer: false,
  },
});

import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Android / iOS app shell (Capacitor). The Angular app is bundled into the app
 * (`npm run build:mobile`) and talks to the live API at vidhisangh.com.
 * See docs/MOBILE.md for the build, signing and store-release steps.
 */
const config: CapacitorConfig = {
  // Permanent store identity: changing it later creates a different app.
  appId: 'com.vidhisangh.app',
  appName: 'VidhiSangh',
  webDir: 'dist-mobile/vidhisangh/browser',
  // Capacitor's bridge log prints every native HTTP call in full, including
  // bearer tokens and the sign-in password. Keep it off in every build.
  loggingBehavior: 'none',
  plugins: {
    // Route fetch/XHR through the native HTTP stack. The API sets its refresh
    // token as an HttpOnly, SameSite=Strict cookie on vidhisangh.com; a
    // WebView served from localhost would never send it (cross-site, and iOS
    // blocks third-party cookies). Native requests use the OS cookie store and
    // are not subject to browser CORS, so the web auth flow works unchanged.
    CapacitorHttp: { enabled: true },
    CapacitorCookies: { enabled: true },
    SplashScreen: {
      launchShowDuration: 3000,
      launchAutoHide: true,
      backgroundColor: '#ffffff',
      showSpinner: false,
    },
    // Live screen updates from our own server (core/platform/live-update.ts).
    // Manual mode: the app decides when to download. Every Capgo cloud call
    // (update checks, stats, crash/health reporting, channels) is switched off.
    CapacitorUpdater: {
      autoUpdate: false,
      updateUrl: 'https://vidhisangh.com/app-updates/latest',
      statsUrl: '',
      channelUrl: '',
      resetWhenUpdate: true,
      autoDeleteFailed: false,
      autoDeletePrevious: true,
      appReadyTimeout: 15000,
    },
    SystemBars: {
      insetsHandling: 'native',
      initialViewportFitValueHint: 'auto',
    },
  },
  android: {
    // Never load http:// content. WebView debugging is left at Capacitor's
    // default: on for debug builds, off for release builds.
    allowMixedContent: false,
  },
  ios: {
    contentInset: 'never',
    limitsNavigationsToAppBoundDomains: false,
  },
};

export default config;

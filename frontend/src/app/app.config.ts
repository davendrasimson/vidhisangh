import {
  ApplicationConfig,
  LOCALE_ID,
  isDevMode,
  provideZoneChangeDetection,
} from '@angular/core';
import { DATE_PIPE_DEFAULT_OPTIONS, registerLocaleData } from '@angular/common';
import localeEnIn from '@angular/common/locales/en-IN';
import { provideRouter, withComponentInputBinding, withViewTransitions } from '@angular/router';
import { provideHttpClient, withInterceptors, withFetch } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideServiceWorker } from '@angular/service-worker';

import { routes } from './app.routes';
import { authInterceptor } from '@core/interceptors/auth.interceptor';
import { errorInterceptor } from '@core/interceptors/error.interceptor';
import { VS_DATE_FORMAT } from '@core/dates/indian-date-adapter';
import { isNativeApp } from '@core/platform/platform';

// Indian conventions everywhere: dd/mm/yyyy dates by default for `| date`,
// and en-IN digit grouping (1,00,000) for `| number` / `| currency`.
registerLocaleData(localeEnIn as object);

export const appConfig: ApplicationConfig = {
  providers: [
    { provide: LOCALE_ID, useValue: 'en-IN' },
    { provide: DATE_PIPE_DEFAULT_OPTIONS, useValue: { dateFormat: VS_DATE_FORMAT } },
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withComponentInputBinding(), withViewTransitions()),
    provideHttpClient(
      withFetch(),
      withInterceptors([authInterceptor, errorInterceptor]),
    ),
    provideAnimationsAsync(),
    provideServiceWorker('ngsw-worker.js', {
      // The app ships its assets in the APK/IPA; a service worker there only
      // serves stale bundles after an app update.
      enabled: !isDevMode() && !isNativeApp(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};

import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { initNativeShell } from './app/core/platform/native-shell';

bootstrapApplication(App, appConfig)
  .then((appRef) => initNativeShell(appRef))
  .catch((err) => console.error(err));

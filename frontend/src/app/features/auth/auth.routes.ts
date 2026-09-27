import { Routes } from '@angular/router';

export const AUTH_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./auth-layout.component').then((m) => m.AuthLayoutComponent),
    children: [
      { path: 'login', loadComponent: () => import('./login/login.component').then((m) => m.LoginComponent) },
      { path: 'register', loadComponent: () => import('./register/register.component').then((m) => m.RegisterComponent) },
      { path: 'callback', loadComponent: () => import('./callback/oauth-callback.component').then((m) => m.OAuthCallbackComponent) },
      { path: '', pathMatch: 'full', redirectTo: 'login' },
    ],
  },
];

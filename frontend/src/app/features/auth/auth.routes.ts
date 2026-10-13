import { Routes } from '@angular/router';

export const AUTH_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./auth-layout.component').then((m) => m.AuthLayoutComponent),
    children: [
      { path: 'login', data: { seo: { title: 'Sign in — VidhiSangh', description: 'Sign in to VidhiSangh with your email and password or a WhatsApp code.' } }, loadComponent: () => import('./login/login.component').then((m) => m.LoginComponent) },
      { path: 'register', data: { seo: { title: 'Join VidhiSangh — free for the legal fraternity', description: 'Create your free VidhiSangh account: a professional profile, network, legal research and bare acts for advocates, students and legal professionals.' } }, loadComponent: () => import('./register/register.component').then((m) => m.RegisterComponent) },
      { path: 'callback', loadComponent: () => import('./callback/oauth-callback.component').then((m) => m.OAuthCallbackComponent) },
      { path: 'forgot', loadComponent: () => import('./forgot/forgot-password.component').then((m) => m.ForgotPasswordComponent) },
      { path: 'reset/:token', loadComponent: () => import('./reset/reset-password.component').then((m) => m.ResetPasswordComponent) },
      { path: 'verify-email/:token', loadComponent: () => import('./verify/verify-email.component').then((m) => m.VerifyEmailComponent) },
      { path: 'change-password', loadComponent: () => import('./change/change-password.component').then((m) => m.ChangePasswordComponent) },
      { path: '', pathMatch: 'full', redirectTo: 'login' },
    ],
  },
];

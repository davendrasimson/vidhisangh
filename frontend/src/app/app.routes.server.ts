import { RenderMode, ServerRoute } from '@angular/ssr';

/**
 * Public pages are rendered to static HTML at build time so search engines
 * and link previews see real content. Everything else (the signed-in app,
 * tokenised client links) stays a client-side page served from index.csr.html.
 */
export const serverRoutes: ServerRoute[] = [
  { path: '', renderMode: RenderMode.Prerender },
  { path: 'help', renderMode: RenderMode.Prerender },
  { path: 'privacy', renderMode: RenderMode.Prerender },
  { path: 'terms', renderMode: RenderMode.Prerender },
  { path: 'about', renderMode: RenderMode.Prerender },
  { path: 'trust', renderMode: RenderMode.Prerender },
  { path: 'auth/login', renderMode: RenderMode.Prerender },
  { path: 'auth/register', renderMode: RenderMode.Prerender },
  { path: '**', renderMode: RenderMode.Client },
];

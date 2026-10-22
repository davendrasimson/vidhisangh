/**
 * Links to vidhisangh.com that open in the app (Android App Links / iOS
 * Universal Links). Must match the paths in AndroidManifest.xml and
 * `/.well-known/assetlinks.json`: anything else stays in the browser,
 * because the app only has its own screens, not the public pages.
 */
export const APP_LINK_HOSTS = ['vidhisangh.com', 'www.vidhisangh.com'];
// /auth/reset/ also carries team invitations.
export const APP_LINK_PREFIXES = ['/app/', '/join/', '/auth/verify-email/', '/auth/reset/'];

/** The in-app route for an opened link, or null if the app should not handle it. */
export function appLinkPath(url: string): string | null {
  let u: URL;
  try { u = new URL(url); } catch { return null; }
  if (u.protocol !== 'https:' || !APP_LINK_HOSTS.includes(u.hostname)) return null;
  const path = u.pathname === '/app' ? '/app/' : u.pathname;
  if (!APP_LINK_PREFIXES.some((p) => path.startsWith(p))) return null;
  return u.pathname + u.search + u.hash;
}

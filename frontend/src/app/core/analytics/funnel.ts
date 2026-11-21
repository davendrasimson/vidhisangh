import { environment } from '@env/environment';

/** Steps of the sign-up funnel (backend app/modules/funnel/router.py STEPS). */
export type FunnelStep = 'landing_view' | 'register_view' | 'email_form_opened' | 'whatsapp_code_requested' | 'invite_prefilled';

/**
 * Count a sign-up step: an anonymous daily counter on our own server (no
 * cookie, no third-party tracker, nothing about the visitor). Once per step per
 * browser tab, so reloads do not inflate it; never during prerendering.
 */
export function countStep(step: FunnelStep): void {
  if (typeof window === 'undefined' || typeof fetch === 'undefined') return;
  try {
    const key = `vs_funnel_${step}`;
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, '1');
  } catch { /* storage unavailable: count anyway */ }
  try {
    void fetch(`${environment.apiBaseUrl}/funnel/${step}`, { method: 'POST', keepalive: true, credentials: 'omit' }).catch(() => undefined);
  } catch { /* never block the page */ }
}

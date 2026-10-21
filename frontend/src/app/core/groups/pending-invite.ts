import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';

const KEY = 'vs_group_invite';

/** A group invite opened before signing up / in; joined once the member is in the app. */
export function rememberGroupInvite(code: string): void {
  try { localStorage.setItem(KEY, code); } catch { /* storage unavailable */ }
}

/** Join the remembered group (if any) and forget it. Returns the group to open, or null. */
export async function joinPendingGroup(http: HttpClient): Promise<{ group_id: string; name: string } | null> {
  let code: string | null = null;
  try { code = localStorage.getItem(KEY); localStorage.removeItem(KEY); } catch { return null; }
  if (!code) return null;
  try {
    return await firstValueFrom(http.post<{ group_id: string; name: string }>(
      `${environment.apiBaseUrl}/groups/invite/${encodeURIComponent(code)}/join`, {}));
  } catch {
    return null;  // the link was reset or the group removed; the error toast says so
  }
}

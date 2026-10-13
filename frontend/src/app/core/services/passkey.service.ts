import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { TokenPair } from '@core/models/auth.models';
import { TokenService } from '@core/auth/token.service';
import { isNativeApp } from '@core/platform/platform';

export interface Passkey {
  id: string;
  name: string;
  credential_id: string;
  last_used_at: string | null;
  created_at: string;
}

/** base64url ⇄ ArrayBuffer helpers for the WebAuthn wire format. */
function b64urlToBuf(value: string): ArrayBuffer {
  const pad = '='.repeat((4 - (value.length % 4)) % 4);
  const b64 = (value + pad).replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

function bufToB64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

@Injectable({ providedIn: 'root' })
export class PasskeyService {
  private readonly http = inject(HttpClient);
  private readonly tokens = inject(TokenService);
  private readonly api = `${environment.apiBaseUrl}/auth/passkeys`;

  static supported(): boolean {
    // Inside the app the page origin is localhost, which the vidhisangh.com
    // passkey (relying party) does not match, so passkeys stay web-only for now.
    return typeof window !== 'undefined' && !!window.PublicKeyCredential && !isNativeApp();
  }

  list(): Observable<Passkey[]> {
    return this.http.get<Passkey[]>(this.api);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${id}`);
  }

  /** Run the registration ceremony against the browser authenticator. */
  async register(name: string): Promise<Passkey> {
    const options = await firstValueFrom(this.http.post<any>(`${this.api}/register/begin`, {}));
    const publicKey = this.toCreateOptions(options);
    const credential = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential;
    const response = this.serializeAttestation(credential);
    return firstValueFrom(
      this.http.post<Passkey>(`${this.api}/register/finish`, { name, response }),
    );
  }

  /** Run the authentication ceremony and return a token pair. */
  async authenticate(email: string): Promise<TokenPair> {
    const options = await firstValueFrom(
      this.http.post<any>(`${this.api}/authenticate/begin`, { email }),
    );
    const publicKey = this.toGetOptions(options);
    const assertion = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential;
    const response = this.serializeAssertion(assertion);
    const pair = await firstValueFrom(
      this.http.post<TokenPair>(`${this.api}/authenticate/finish`, { response }, { withCredentials: true }),
    );
    this.tokens.setSession(pair);
    return pair;
  }

  // ── Wire-format mapping (real backend emits standard WebAuthn options) ──
  private toCreateOptions(o: any): PublicKeyCredentialCreationOptions {
    return {
      ...o,
      challenge: b64urlToBuf(o.challenge),
      user: { ...o.user, id: b64urlToBuf(o.user.id) },
      excludeCredentials: (o.excludeCredentials ?? []).map((c: any) => ({
        ...c,
        id: b64urlToBuf(c.id),
      })),
    };
  }

  private toGetOptions(o: any): PublicKeyCredentialRequestOptions {
    return {
      ...o,
      challenge: b64urlToBuf(o.challenge),
      allowCredentials: (o.allowCredentials ?? []).map((c: any) => ({
        ...c,
        type: 'public-key',
        id: b64urlToBuf(c.id),
      })),
    };
  }

  private serializeAttestation(cred: PublicKeyCredential): Record<string, unknown> {
    const r = cred.response as AuthenticatorAttestationResponse;
    return {
      id: cred.id,
      rawId: bufToB64url(cred.rawId),
      type: cred.type,
      response: {
        clientDataJSON: bufToB64url(r.clientDataJSON),
        attestationObject: bufToB64url(r.attestationObject),
      },
    };
  }

  private serializeAssertion(cred: PublicKeyCredential): Record<string, unknown> {
    const r = cred.response as AuthenticatorAssertionResponse;
    return {
      id: cred.id,
      rawId: bufToB64url(cred.rawId),
      type: cred.type,
      response: {
        clientDataJSON: bufToB64url(r.clientDataJSON),
        authenticatorData: bufToB64url(r.authenticatorData),
        signature: bufToB64url(r.signature),
        userHandle: r.userHandle ? bufToB64url(r.userHandle) : null,
      },
    };
  }
}

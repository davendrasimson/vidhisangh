/** API contracts mirrored from the backend identity module. */

export interface TokenPair {
  access_token: string;
  /** Null once the API stops echoing it: the refresh token lives in an HttpOnly cookie. */
  refresh_token: string | null;
  token_type: 'bearer';
  expires_in: number;
  /** True when this session may only call /auth/change-password (temporary password). */
  password_must_change?: boolean;
}

export interface RegisterRequest {
  organisation_name: string;
  full_name: string;
  email: string;
  password: string;
  accept_terms: boolean;
  device_id?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
  tenant_slug?: string | null;
  mfa_code?: string | null;
  device_label?: string | null;
  device_id?: string | null;
}

export interface Role {
  id: string;
  code: string;
  name: string;
  is_system: boolean;
}

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  display_name: string | null;
  avatar_url: string | null;
  is_active: boolean;
  is_email_verified: boolean;
  is_superuser: boolean;
  mfa_enabled: boolean;
  password_must_change?: boolean;
  terms_version: string | null;
  terms_accepted_at: string | null;
  last_login_at: string | null;
  roles: Role[];
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  type: string;
  status: string;
  plan: string;
  region: string;
  created_at: string;
}

export interface SsoProvider {
  name: string;
  display_name: string;
}

export interface AuthSession {
  id: string;
  device_label: string | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface OAuthAuthorize {
  authorize_url: string;
  state: string;
}

/** RFC-9457-style problem document returned by the API on errors. */
export interface ApiProblem {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  request_id?: string;
  errors?: unknown;
}

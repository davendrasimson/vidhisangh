/** API-key contracts (mirrors the backend apikeys module). */

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  last_used_at: string | null;
  expires_at: string | null;
  revoked: boolean;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKey {
  key: string; // full plaintext — shown only once
}

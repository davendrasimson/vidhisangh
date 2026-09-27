/** System dashboard contracts (mirrors the backend health/system module). */

export interface AppInfo {
  name: string;
  version: string;
  environment: string;
}

export interface Check {
  name: string;
  status: string; // "ok" | "error" | "unreachable"
  detail: string | null;
}

export interface Integration {
  name: string;
  key: string;
  status: string; // "live" | "log-fallback" | "mock" | value
}

export interface ChannelStatus {
  channel: string;
  provider: string;
  status: string; // "live" | "log-fallback" | "not_configured"
}

export interface SystemOverview {
  app: AppInfo;
  migration: string | null;
  checks: Check[];
  integrations: Integration[];
  channels: ChannelStatus[];
}

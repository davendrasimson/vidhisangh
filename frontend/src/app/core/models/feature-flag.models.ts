/** Feature-flag contracts (mirrors the backend featureflags module). */

export interface FeatureFlag {
  key: string;
  name: string;
  description: string;
  enabled: boolean;
  default: boolean;
  overridden: boolean;
}

/** Resolved on/off map for the current tenant, keyed by flag key. */
export type ResolvedFlags = Record<string, boolean>;

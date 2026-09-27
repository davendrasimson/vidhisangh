/** Subscription plan contracts (mirrors the backend plans module). */

export type PlanTier = 'free' | 'solo' | 'team' | 'firm' | 'enterprise';
export type TenantStatus = 'trial' | 'active' | 'suspended' | 'cancelled';

export interface Plan {
  tier: PlanTier;
  name: string;
  price_inr: number | null; // null = custom / contact sales
  max_users: number | null; // null = unlimited
  max_matters: number | null;
  storage_gb: number | null;
  features: string[];
  is_current: boolean;
}

export interface Usage {
  users: number;
  matters: number;
}

export interface Subscription {
  plan: Plan;
  status: TenantStatus;
  usage: Usage;
}

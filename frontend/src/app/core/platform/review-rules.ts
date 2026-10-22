/** When to ask for a store rating (pure, so it can be unit-tested). */
export const MIN_DAYS = 5;
export const MIN_LAUNCHES = 8;
export const GAP_DAYS = 120;
const DAY = 86_400_000;

export interface ReviewState { firstOpen: number; launches: number; lastAsked: number | null }

/** Count this launch; true when it is time to ask (and records the ask). */
export function countLaunchAndDecide(state: ReviewState | null, now: number): { state: ReviewState; ask: boolean } {
  const s = state ?? { firstOpen: now, launches: 0, lastAsked: null };
  const next = { ...s, launches: s.launches + 1 };
  const ask = next.launches >= MIN_LAUNCHES && now - next.firstOpen >= MIN_DAYS * DAY 
    && (next.lastAsked === null || now - next.lastAsked >= GAP_DAYS * DAY);
  return { state: ask ? { ...next, lastAsked: now } : next, ask };
}

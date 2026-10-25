import type { ProfileDetail } from '@core/models/profile.models';

/**
 * How complete a professional profile is, and the one thing to add next.
 * Students and judges are not asked for enrolment details.
 */
export interface ProfileStep { key: string; label: string; done: boolean }

export function profileSteps(p: ProfileDetail): ProfileStep[] {
  const role = p.professional_role ?? '';
  const practising = !['law_student', 'judicial_officer', 'retired_judicial_officer'].includes(role);
  const steps: ProfileStep[] = [
    { key: 'role', label: 'what best describes you', done: !!role },
    { key: 'headline', label: 'a one-line headline', done: !!p.headline?.trim() },
    { key: 'city', label: 'your city', done: !!p.city?.trim() },
    { key: 'practice_areas', label: 'your practice areas', done: p.practice_areas.length > 0 },
    { key: 'courts', label: role === 'judicial_officer' ? 'the court you preside over' : 'the courts you appear in', done: p.courts.length > 0 },
    { key: 'bio', label: 'a few lines about yourself', done: (p.bio?.trim().length ?? 0) >= 40 },
  ];
  if (practising) steps.push({ key: 'enrolment', label: 'your Bar Council and year of enrolment', done: !!p.bar_council && !!p.year_of_enrollment });
  if (role === 'law_student') steps.splice(3, 2, { key: 'education', label: 'your law school', done: p.education.length > 0 });
  return steps;
}

export function profilePercent(steps: ProfileStep[]): number {
  return steps.length ? Math.round((steps.filter((s) => s.done).length / steps.length) * 100) : 0;
}

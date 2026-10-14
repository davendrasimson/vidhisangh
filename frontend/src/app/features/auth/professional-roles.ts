/** Job profiles offered at sign-up (values from the profile masters), the common ones first. */
export const PROFESSIONAL_ROLES = [
  { value: 'advocate', label: 'Advocate' },
  { value: 'law_student', label: 'Law Student' },
  { value: 'judicial_officer', label: 'Judicial Officer' },
  { value: 'in_house_counsel', label: 'Corporate / In-house Counsel' },
  { value: 'senior_advocate', label: 'Senior Advocate' },
  { value: 'retired_judicial_officer', label: 'Retired Judicial Officer' },
  { value: 'arbitrator', label: 'Arbitrator / Mediator' },
  { value: 'law_officer', label: 'Government Law Officer' },
  { value: 'law_teacher', label: 'Law Teacher / Academic' },
  { value: 'paralegal', label: 'Paralegal' },
  { value: 'clerk', label: 'Court Clerk / Munshi' },
  { value: 'other', label: 'Other legal professional' },
] as const;

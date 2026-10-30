/** Professional profile API contracts (mirrors the backend profile module). */

export type VerificationStatus = 'unverified' | 'pending' | 'verified' | 'rejected';
export type ProfileVisibility = 'public' | 'connections' | 'private';
export type GroupVisibility = 'everyone' | 'connections' | 'followers' | 'none';

export interface EducationItem {
  institution: string;
  degree?: string | null;
  level?: string | null;
  field_of_study?: string | null;
  start_year?: number | null;
  year?: number | null;
}

export interface EmploymentItem { organisation: string; designation?: string | null; from_year?: number | null; to_year?: number | null; current?: boolean; }
export interface MembershipItem { organisation: string; membership_number?: string | null; year?: number | null; }
export interface MasterOption { value: string; label: string; }
export interface ProfileMasters {
  professional_roles: MasterOption[]; degrees: MasterOption[]; education_levels: MasterOption[];
  practice_areas: string[]; bar_councils: string[]; states: string[]; cities_by_state: Record<string, string[]>;
  courts: string[]; languages: string[]; visibility_options: MasterOption[];
}

export interface PublicationItem {
  title: string;
  publisher?: string | null;
  year?: number | null;
  url?: string | null;
}

export interface ProfileDetail {
  id: string;
  user_id: string;
  headline: string | null;
  bio: string | null;
  professional_role: string | null;
  designation: string | null;
  enrollment_number: string | null;
  bar_council: string | null;
  year_of_enrollment: number | null;
  years_of_experience: number | null;
  practice_areas: string[];
  courts: string[];
  languages: string[];
  education: EducationItem[];
  achievements: string[];
  publications: PublicationItem[];
  employment_history: EmploymentItem[];
  memberships: MembershipItem[];
  city: string | null;
  state: string | null;
  office_address: string | null;
  website: string | null;
  linkedin_url: string | null;
  professional_email: string | null;
  professional_phone: string | null;
  postal_code: string | null;
  judicial_court_name: string | null;
  judicial_court_address: string | null;
  judicial_district: string | null;
  judicial_state: string | null;
  judicial_officer_code: string | null;
  consultation_enabled: boolean;
  consultation_fee: string | number | null;
  availability: Record<string, unknown>;
  verification_status: VerificationStatus;
  visibility: ProfileVisibility;
  visibility_settings: Record<string, GroupVisibility>;
  masked_groups: string[];
  avg_rating: string | number | null;
  rating_count: number;
  endorsement_summary: Record<string, number>;
  recommendations: Recommendation[];
}

export interface Recommendation {
  id: string;
  author_user_id: string;
  relationship_context: string | null;
  body: string;
  created_at: string;
}

export interface ProfileUpdate {
  headline?: string | null;
  bio?: string | null;
  professional_role?: string | null;
  designation?: string | null;
  enrollment_number?: string | null;
  bar_council?: string | null;
  year_of_enrollment?: number | null;
  years_of_experience?: number | null;
  practice_areas?: string[];
  courts?: string[];
  languages?: string[];
  education?: EducationItem[];
  achievements?: string[];
  publications?: PublicationItem[];
  employment_history?: EmploymentItem[];
  memberships?: MembershipItem[];
  city?: string | null;
  state?: string | null;
  office_address?: string | null;
  website?: string | null;
  linkedin_url?: string | null;
  professional_email?: string | null;
  professional_phone?: string | null;
  postal_code?: string | null;
  judicial_court_name?: string | null;
  judicial_court_address?: string | null;
  judicial_district?: string | null;
  judicial_state?: string | null;
  judicial_officer_code?: string | null;
  consultation_enabled?: boolean;
  consultation_fee?: number | null;
  visibility?: ProfileVisibility;
  visibility_settings?: Record<string, GroupVisibility>;
}

export interface BarVerificationRequest {
  enrollment_number: string;
  bar_council: string;
  document_url?: string | null;
}

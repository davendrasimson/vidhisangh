/** Professional profile API contracts (mirrors the backend profile module). */

export type VerificationStatus = 'unverified' | 'pending' | 'verified' | 'rejected';
export type ProfileVisibility = 'public' | 'connections' | 'private';

export interface EducationItem {
  institution: string;
  degree?: string | null;
  year?: number | null;
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
  city: string | null;
  state: string | null;
  office_address: string | null;
  website: string | null;
  linkedin_url: string | null;
  consultation_enabled: boolean;
  consultation_fee: string | number | null;
  availability: Record<string, unknown>;
  verification_status: VerificationStatus;
  visibility: ProfileVisibility;
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
  city?: string | null;
  state?: string | null;
  office_address?: string | null;
  website?: string | null;
  linkedin_url?: string | null;
  consultation_enabled?: boolean;
  consultation_fee?: number | null;
  visibility?: ProfileVisibility;
}

export interface BarVerificationRequest {
  enrollment_number: string;
  bar_council: string;
  document_url?: string | null;
}

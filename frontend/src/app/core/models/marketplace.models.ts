/** Marketplace API contracts (mirrors the backend marketplace module). */

export type ListingType =
  | 'referral' | 'local_counsel' | 'expert' | 'researcher' | 'arbitrator' | 'job' | 'internship';
export type ListingStatus = 'open' | 'closed';

export interface Listing {
  id: string;
  type: ListingType;
  title: string;
  description: string;
  practice_area: string | null;
  location: string | null;
  budget: string | number | null;
  status: ListingStatus;
  posted_by: string;
  poster_name: string;
  response_count: number;
  matter_id: string | null;
  accepted_response_id: string | null;
  created_at: string;
}

export interface ListingResponse {
  id: string;
  listing_id: string;
  responder_id: string;
  responder_name: string;
  responder_email: string | null;
  message: string;
  created_at: string;
}

export interface ListingCreate {
  type: ListingType;
  title: string;
  description: string;
  practice_area?: string | null;
  location?: string | null;
  budget?: number | null;
  matter_id?: string | null;
}

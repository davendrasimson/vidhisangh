/** Client master API contracts (mirrors the backend clients module). */

export type ClientKind = 'individual' | 'business';
export type ClientStatus = 'active' | 'inactive';
export type GstTreatment =
  | 'unregistered' | 'registered_regular' | 'registered_composition' | 'sez' | 'overseas' | 'government';
export type KycStatus = 'not_started' | 'pending' | 'submitted' | 'verified';
export type KycRequestStatus = 'sent' | 'submitted' | 'applied' | 'expired' | 'cancelled';

export const GST_TREATMENTS: { value: GstTreatment; label: string }[] = [
  { value: 'unregistered', label: 'Unregistered' },
  { value: 'registered_regular', label: 'Registered — regular' },
  { value: 'registered_composition', label: 'Registered — composition' },
  { value: 'sez', label: 'SEZ unit / developer' },
  { value: 'overseas', label: 'Overseas (export of services)' },
  { value: 'government', label: 'Government / local authority' },
];

export const BUSINESS_TYPE_LABELS: Record<string, string> = {
  proprietorship: 'Sole proprietorship', partnership: 'Partnership firm', llp: 'LLP',
  private_limited: 'Private limited company', public_limited: 'Public limited company', opc: 'One person company',
  trust: 'Trust', society: 'Society', huf: 'HUF', government: 'Government department', psu: 'PSU',
  cooperative: 'Co-operative society', foreign_entity: 'Foreign entity', other: 'Other',
};

export interface ValidationIssue {
  field: string;
  message: string;
  severity: 'error' | 'warning';
}

/** Every editable field; all optional so the same shape serves create, update and KYC. */
export interface ClientFields {
  display_name?: string | null;
  client_code?: string | null;
  status?: ClientStatus | null;
  first_name?: string | null;
  last_name?: string | null;
  date_of_birth?: string | null;
  father_or_spouse_name?: string | null;
  occupation?: string | null;
  legal_name?: string | null;
  trade_name?: string | null;
  business_type?: string | null;
  cin?: string | null;
  incorporation_date?: string | null;
  contact_person_name?: string | null;
  contact_person_designation?: string | null;
  contact_person_email?: string | null;
  contact_person_mobile?: string | null;
  pan?: string | null;
  email?: string | null;
  phone?: string | null;
  mobile?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  state_code?: string | null;
  pincode?: string | null;
  country?: string | null;
  consent_email?: boolean | null;
  consent_mobile?: boolean | null;
  consent_whatsapp?: boolean | null;
  gst_applicable?: boolean | null;
  gstin?: string | null;
  gst_treatment?: GstTreatment | null;
  reverse_charge?: boolean | null;
  place_of_supply_code?: string | null;
  tds_applicable?: boolean | null;
  tds_section?: string | null;
  tds_rate?: number | null;
  tan?: string | null;
  msme_udyam?: string | null;
  notes?: string | null;
  tags?: string[] | null;
  // DPDP s.9: a minor needs a recorded guardian consent before KYC can be sent.
  is_minor?: boolean | null;
  guardian_name?: string | null;
  guardian_relation?: string | null;
}

export interface ClientSummary {
  id: string;
  kind: ClientKind;
  status: ClientStatus;
  client_code: string | null;
  display_name: string;
  email: string | null;
  mobile: string | null;
  city: string | null;
  state: string | null;
  pan: string | null;
  gstin: string | null;
  gst_applicable: boolean;
  tds_applicable: boolean;
  kyc_status: KycStatus;
  updated_at: string;
  created_at: string;
}

export interface Client extends ClientSummary, Required<Omit<ClientFields, keyof ClientSummary | 'tags'>> {
  tags: string[];
  consent_recorded_at: string | null;
  consent_source: string | null;
  guardian_consent_recorded_at: string | null;
  kyc_verified_at: string | null;
  kyc_verified_by: string | null;
  created_by: string;
  updated_by: string;
  issues: ValidationIssue[];
}

export interface ClientCreate extends ClientFields {
  kind: ClientKind;
  display_name: string;
}

export interface ReferenceData {
  tds_sections: { section: string; label: string; rate: number }[];
  business_types: string[];
  states: { code: string; name: string }[];
}

export interface KycRequest {
  id: string;
  client_id: string;
  status: KycRequestStatus;
  sent_to_email: string | null;
  sent_to_mobile: string | null;
  message: string | null;
  expires_at: string;
  submitted_at: string | null;
  applied_at: string | null;
  initiated_by: string;
  created_at: string;
  issues: ValidationIssue[];
  url: string | null;
}

export interface KycChange {
  field: string;
  current: unknown;
  submitted: unknown;
}

export interface KycRequestDetail extends KycRequest {
  prefill: ClientFields;
  submitted_data: ClientFields | null;
  changes: KycChange[];
}

export interface KycPublicView {
  firm_name: string;
  client_kind: ClientKind;
  display_name: string;
  message: string | null;
  expires_at: string;
  status: KycRequestStatus;
  prefill: ClientFields;
  tds_sections: ReferenceData['tds_sections'];
  business_types: string[];
  states: ReferenceData['states'];
}

export interface KycSubmitResult {
  status: KycRequestStatus;
  issues: ValidationIssue[];
  message: string;
}

/** Human labels for fields, used by the KYC diff and issue lists. */
export const FIELD_LABELS: Record<string, string> = {
  display_name: 'Name', client_code: 'Client code', first_name: 'First name', last_name: 'Last name',
  date_of_birth: 'Date of birth', father_or_spouse_name: "Father's / spouse's name", occupation: 'Occupation',
  legal_name: 'Legal name', trade_name: 'Trade name', business_type: 'Business type', cin: 'CIN',
  incorporation_date: 'Incorporation date', contact_person_name: 'Contact person',
  contact_person_designation: 'Designation', contact_person_email: 'Contact email', contact_person_mobile: 'Contact mobile',
  pan: 'PAN', email: 'Email', phone: 'Phone', mobile: 'Mobile', address_line1: 'Address line 1',
  address_line2: 'Address line 2', city: 'City', state: 'State', state_code: 'State code', pincode: 'PIN code',
  country: 'Country', consent_email: 'Consent — email', consent_mobile: 'Consent — SMS / calls',
  consent_whatsapp: 'Consent — WhatsApp', gst_applicable: 'GST applicable', gstin: 'GSTIN',
  gst_treatment: 'GST treatment', reverse_charge: 'Reverse charge', place_of_supply_code: 'Place of supply',
  tds_applicable: 'Deducts TDS', tds_section: 'TDS section', tds_rate: 'TDS rate (%)', tan: 'TAN',
  msme_udyam: 'Udyam (MSME) number', notes: 'Notes', tags: 'Tags',
};

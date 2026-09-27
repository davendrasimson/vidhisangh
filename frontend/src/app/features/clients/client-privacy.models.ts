/** Privacy additions to the client contracts (kept beside the clients feature). */

import { ClientFields, KycPublicView } from '@core/models/clients.models';

export type ConsentPurpose =
  | 'contact_email' | 'contact_sms' | 'contact_whatsapp'
  | 'processing_case' | 'processing_billing' | 'processing_filing' | 'marketing' | 'guardian_consent';

export const CONSENT_PURPOSE_LABELS: Record<ConsentPurpose, string> = {
  contact_email: 'Contact by e-mail',
  contact_sms: 'Contact by SMS / phone',
  contact_whatsapp: 'Contact by WhatsApp',
  processing_case: 'Processing for the matter',
  processing_billing: 'Processing for billing',
  processing_filing: 'Processing for filings',
  marketing: 'Marketing / newsletters',
  guardian_consent: "Parent's / guardian's consent (minor)",
};

export interface ConsentEvent {
  id: string;
  client_id: string;
  purpose: ConsentPurpose;
  granted: boolean;
  source: 'staff' | 'kyc_form' | 'portal';
  notice_version: string | null;
  actor_id: string | null;
  recorded_at: string;
  ip_coarse: string | null;
  note: string | null;
}

/** Fields added to the client by the privacy work (DPDP s.9 minors). */
export interface PrivacyClientFields {
  is_minor?: boolean | null;
  guardian_name?: string | null;
  guardian_relation?: string | null;
}

export type ClientFormFields = ClientFields & PrivacyClientFields;

export interface LegalHold {
  matter_id: string;
  matter_number: string;
  reason: string;
  closed_on?: string | null;
}

export interface ClientEraseResult {
  client_id: string;
  erased: boolean;
  unlinked: Record<string, number>;
  legal_hold_overridden: boolean;
}

export interface PrivacyNoticeSummary {
  version: string;
  purposes: string[];
  retention: string;
  rights: string[];
  grievance_officer: { name: string; email: string; address: string };
  notice_url: string;
  firm_is_fiduciary: boolean;
}

/** The public KYC view now carries the DPDP notice block. */
export type KycPublicViewWithNotice = KycPublicView & { notice?: PrivacyNoticeSummary };

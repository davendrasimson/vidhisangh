/** Document management API contracts (mirrors the backend documents module). */

export interface DocFolder {
  id: string;
  name: string;
  parent_id: string | null;
  matter_id: string | null;
  created_at: string;
}

export interface DocFile {
  id: string;
  name: string;
  folder_id: string | null;
  matter_id: string | null;
  client_id: string | null;
  client_name: string | null;
  content_type: string;
  size: number;
  tags: string[];
  current_version_id: string | null;
  version_count: number;
  locked_by: string | null;
  locked_at: string | null;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
}

export interface DocVersion {
  id: string;
  document_id: string;
  version_no: number;
  size: number;
  content_type: string;
  checksum: string;
  comment: string | null;
  uploaded_by: string;
  created_at: string;
}

export type SignerKind = 'internal' | 'external';
export type SignatureStatus = 'waiting' | 'pending' | 'signed' | 'rejected' | 'cancelled';
export interface SignatureStep {
  id: string; step_order: number; signer_kind: SignerKind; signer_user_id: string | null;
  signer_name: string; signer_email: string; designation: string | null;
  status: SignatureStatus; signed_at: string | null; rejected_at: string | null;
  signed_name: string | null; remarks: string | null;
}
export interface SignatureEvent { id: string; event_type: string; actor_label: string | null; detail: Record<string, unknown>; created_at: string; }
export interface SignatureEnvelope {
  id: string; document_id: string; document_name: string; source_version_id: string;
  source_checksum: string; title: string; message: string;
  status: 'pending' | 'completed' | 'rejected' | 'cancelled'; sequential: boolean;
  created_by: string; sent_at: string; completed_at: string | null; final_checksum: string | null;
  steps: SignatureStep[]; events: SignatureEvent[];
}
export interface SignatureSignerInput { kind: SignerKind; user_id?: string | null; name: string; email: string; designation?: string | null; }
export interface PublicSignatureStep { document_title: string; sender_message: string; signer_name: string; designation: string | null; status: SignatureStatus; expires_at: string | null; requires_otp: boolean; }

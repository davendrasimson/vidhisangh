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

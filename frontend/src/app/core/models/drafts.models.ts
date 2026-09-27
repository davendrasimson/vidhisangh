/** Drafting API contracts (mirrors the backend drafting module). */

export type DraftStatus = 'draft' | 'final';
export type PageSize = 'A4' | 'Letter' | 'Legal';
export type PageOrientation = 'portrait' | 'landscape';

export interface PageMargins {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** Page geometry in millimetres — what the canvas shows and the DOCX uses. */
export interface PageSettings {
  size: PageSize;
  orientation: PageOrientation;
  margins: PageMargins;
}

export const DEFAULT_PAGE: PageSettings = {
  size: 'A4',
  orientation: 'portrait',
  margins: { top: 25.4, right: 25.4, bottom: 25.4, left: 25.4 },
};

export const PAGE_SIZES_MM: Record<PageSize, [number, number]> = {
  A4: [210, 297],
  Letter: [215.9, 279.4],
  Legal: [215.9, 355.6],
};

/** The editor's document — ProseMirror JSON. Opaque to the app. */
export type EditorDoc = { type: 'doc'; content?: unknown[] } & Record<string, unknown>;

export interface DraftSummary {
  id: string;
  title: string;
  language: string;
  template_id: string | null;
  matter_id: string | null;
  client_id: string | null;
  client_name: string | null;
  status: DraftStatus;
  word_count: number;
  version_count: number;
  library_document_id: string | null;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface Draft extends DraftSummary {
  content_json: EditorDoc;
  content_html: string;
  page: PageSettings;
}

export interface DraftCreate {
  title?: string;
  language?: string;
  template_id?: string | null;
  matter_id?: string | null;
  client_id?: string | null;
  content_json?: EditorDoc;
  content_html?: string;
  page?: PageSettings;
}

export interface DraftUpdate {
  title?: string;
  language?: string;
  matter_id?: string | null;
  client_id?: string | null;
  status?: DraftStatus;
  content_json?: EditorDoc;
  content_html?: string;
  page?: PageSettings;
}

export interface DraftVersion {
  id: string;
  version_no: number;
  note: string | null;
  word_count: number;
  created_by: string;
  created_at: string;
}

export interface DraftVersionDetail extends DraftVersion {
  content_json: EditorDoc;
  content_html: string;
}

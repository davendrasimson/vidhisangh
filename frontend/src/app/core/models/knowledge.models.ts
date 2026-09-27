/** Knowledge base API contracts (mirrors the backend knowledge module). */

export type KnowledgeCategory = 'template' | 'precedent' | 'sop' | 'checklist' | 'note';

export interface KnowledgeSummary {
  id: string;
  title: string;
  category: KnowledgeCategory;
  practice_area: string | null;
  tags: string[];
  updated_at: string;
}

export interface KnowledgeItem extends KnowledgeSummary {
  body: string;
  source_url: string | null;
  reviewed_on: string | null;
  attachments: string[];
  created_by: string;
  created_at: string;
}

export interface KnowledgeCreate {
  title: string;
  category?: KnowledgeCategory;
  body: string;
  practice_area?: string | null;
  tags?: string[];
  source_url?: string | null;
  reviewed_on?: string | null;
  attachments?: string[];
}

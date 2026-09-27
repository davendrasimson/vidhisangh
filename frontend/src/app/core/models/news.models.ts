/** Legal news API contracts (mirrors the backend news module). */

export type NewsCategory = 'judgment' | 'legislation' | 'notification' | 'circular' | 'news';

export interface NewsItem {
  id: string;
  title: string;
  summary: string | null;
  source: string;
  category: NewsCategory;
  url: string | null;
  image_url: string | null;
  published_at: string;
  tags: string[];
}

export interface NewsItemCreate {
  title: string;
  summary?: string | null;
  source: string;
  category?: NewsCategory;
  url?: string | null;
  image_url?: string | null;
  published_at: string;
  tags?: string[];
}

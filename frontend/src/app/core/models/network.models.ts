/** Professional network API contracts (mirrors the backend network module). */

export type ReactionType = 'like' | 'insightful' | 'celebrate' | 'support' | 'curious';
export type PostReportCategory = 'spam' | 'harassment' | 'hate_or_abuse' | 'misinformation' | 'privacy' | 'impersonation' | 'other';
export interface PostReportResult { ticket_number: string; status: string; }
export type PostVisibility = 'public' | 'connections';
export type PostType = 'text' | 'article' | 'announcement';
export type ConnectionStatus = 'pending' | 'accepted' | 'declined';

export interface Mention {
  user_id: string;
  name: string;
}

export interface FeedItem {
  id: string;
  author_id: string;
  author_name: string;
  author_headline: string | null;
  author_avatar_url: string | null;
  post_type: PostType;
  title: string | null;
  content: string;
  /** Formatted body (server-cleaned HTML); null for plain-text posts. */
  content_html?: string | null;
  images?: PostImage[];
  visibility: PostVisibility;
  hashtags: string[];
  like_count: number;
  comment_count: number;
  share_count: number;
  created_at: string;
  // Link preview (Open Graph unfurl) snapshot.
  link_url: string | null;
  link_title: string | null;
  link_description: string | null;
  link_image: string | null;
  link_site_name: string | null;
  my_reaction: ReactionType | null;
  bookmarked: boolean;
  // Repost snapshot of the original (present when this post is a share).
  shared_from_id: string | null;
  shared_author_name: string | null;
  shared_author_avatar_url: string | null;
  shared_content: string | null;
  /** The original's photos on a repost (while the original exists). */
  shared_images?: PostImage[];
  shared_created_at: string | null;
  mentions: Mention[];
}

export interface LinkPreview {
  url: string;
  title: string | null;
  description: string | null;
  image: string | null;
  site_name: string | null;
}

export interface PostImage { id: string; width: number; height: number; }

export interface PostCreate {
  content: string;
  content_html?: string | null;
  image_ids?: string[];
  title?: string | null;
  post_type?: PostType;
  visibility?: PostVisibility;
  hashtags?: string[];
  mention_ids?: string[];
  link_url?: string | null;
  link_title?: string | null;
  link_description?: string | null;
  link_image?: string | null;
  link_site_name?: string | null;
}

export interface Comment {
  id: string;
  post_id: string;
  parent_id: string | null;
  author_id: string;
  author_name: string;
  author_avatar_url: string | null;
  body: string;
  created_at: string;
}

export interface DirectoryPerson {
  user_id: string;
  display_name: string;
  headline: string | null;
  avatar_url: string | null;
  city: string | null;
  is_verified: boolean;
  connection_status: 'connected' | 'pending_out' | 'pending_in' | null;
  is_following: boolean;
}

export interface PublicProfile extends DirectoryPerson {
  is_self: boolean;
}

export interface Connection {
  id: string;
  requester_id: string;
  addressee_id: string;
  status: ConnectionStatus;
  message: string | null;
  created_at: string;
  /** Who sent it: on incoming requests (null if they left the network). */
  requester?: Pick<DirectoryPerson, 'user_id' | 'display_name' | 'headline' | 'avatar_url' | 'city' | 'is_verified'> | null;
}

export interface TrendingTag {
  tag: string;
  count: number;
}

/** One official daily post as a home-screen card. */
export interface DailyCard {
  kind: 'section' | 'judgment' | 'news';
  /** "bns:318", a judgment id, or a news item id. */
  ref: string;
  post_id: string;
  title: string;
  description: string | null;
  url: string | null;
  site: string | null;
  posted_at: string;
}

export interface DailyRead {
  section: DailyCard | null;
  judgment: DailyCard | null;
  news: DailyCard[];
}

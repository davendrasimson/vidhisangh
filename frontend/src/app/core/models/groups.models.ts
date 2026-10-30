/** Groups / communities / firm-pages API contracts (mirrors the backend groups module). */

export type GroupType = 'community' | 'firm';
export type GroupVisibility = 'public' | 'private';
export type MemberRole = 'owner' | 'admin' | 'member';
export type MemberStatus = 'active' | 'pending';

export interface Group {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  group_type: GroupType;
  visibility: GroupVisibility;
  avatar_url: string | null;
  cover_url: string | null;
  owner_id: string;
  tenant_id: string | null;
  is_verified: boolean;
  member_count: number;
  post_count: number;
  created_at: string;
  my_role: MemberRole | null;
  my_status: MemberStatus | null;
}

export interface GroupCreate {
  name: string;
  description?: string | null;
  group_type?: GroupType;
  visibility?: GroupVisibility;
  slug?: string | null;
}

export interface GroupUpdate {
  name?: string;
  description?: string | null;
  visibility?: GroupVisibility;
  avatar_url?: string | null;
  cover_url?: string | null;
}

export interface GroupMember {
  id: string;
  group_id: string;
  user_id: string;
  member_name: string;
  member_headline: string | null;
  member_avatar_url: string | null;
  role: MemberRole;
  status: MemberStatus;
  created_at: string;
}

export interface GroupPost {
  id: string;
  group_id: string;
  author_id: string;
  author_name: string;
  author_avatar_url: string | null;
  content: string;
  /** Formatted body (server-cleaned HTML); null for plain-text posts. */
  content_html?: string | null;
  images?: { id: string; width: number; height: number }[];
  like_count: number;
  comment_count: number;
  created_at: string;
  liked: boolean;
}

/** A post on the home screen's "latest in your groups" card: the post plus its group. */
export interface GroupFeedItem extends GroupPost {
  group_name: string;
  group_slug: string;
}

export interface GroupComment {
  id: string;
  group_post_id: string;
  author_id: string;
  author_name: string;
  author_avatar_url: string | null;
  body: string;
  created_at: string;
}

export interface Invitation {
  group_id: string;
  group_name: string;
  group_slug: string;
  group_type: GroupType;
  visibility: GroupVisibility;
  member_count: number;
  invited_at: string;
}

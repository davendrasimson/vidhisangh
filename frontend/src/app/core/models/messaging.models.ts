/** Messaging API contracts (mirrors the backend messaging module). */

export type ConversationType = 'direct' | 'group';

export interface Participant {
  user_id: string;
  participant_name: string;
  participant_avatar_url: string | null;
}

export interface Conversation {
  id: string;
  type: ConversationType;
  title: string | null;
  created_by: string;
  last_message_at: string | null;
  last_message_preview: string | null;
  created_at: string;
  participants: Participant[];
  unread_count: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  sender_name: string;
  sender_avatar_url: string | null;
  body: string;
  created_at: string;
}

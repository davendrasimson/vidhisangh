import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  Group,
  GroupComment,
  GroupCreate,
  GroupMember,
  GroupPost,
  GroupType,
  GroupUpdate,
  Invitation,
  MemberRole,
} from '@core/models/groups.models';

@Injectable({ providedIn: 'root' })
export class GroupsService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/groups`;

  // ── Discovery & lifecycle ─────────────────────────────────────
  discover(type?: GroupType, page = 1, size = 30): Observable<Group[]> {
    const params: Record<string, string | number> = { page, size };
    if (type) params['type'] = type;
    return this.http.get<Group[]>(this.api, { params });
  }

  myGroups(): Observable<Group[]> {
    return this.http.get<Group[]>(`${this.api}/mine`);
  }

  get(groupId: string): Observable<Group> {
    return this.http.get<Group>(`${this.api}/${groupId}`);
  }

  create(payload: GroupCreate): Observable<Group> {
    return this.http.post<Group>(this.api, payload);
  }

  update(groupId: string, payload: GroupUpdate): Observable<Group> {
    return this.http.patch<Group>(`${this.api}/${groupId}`, payload);
  }

  remove(groupId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${groupId}`);
  }

  // ── Membership ────────────────────────────────────────────────
  join(groupId: string): Observable<GroupMember> {
    return this.http.post<GroupMember>(`${this.api}/${groupId}/join`, {});
  }

  leave(groupId: string): Observable<void> {
    return this.http.post<void>(`${this.api}/${groupId}/leave`, {});
  }

  members(groupId: string): Observable<GroupMember[]> {
    return this.http.get<GroupMember[]>(`${this.api}/${groupId}/members`);
  }

  requests(groupId: string): Observable<GroupMember[]> {
    return this.http.get<GroupMember[]>(`${this.api}/${groupId}/requests`);
  }

  approve(groupId: string, userId: string): Observable<GroupMember> {
    return this.http.post<GroupMember>(`${this.api}/${groupId}/members/${userId}/approve`, {});
  }

  reject(groupId: string, userId: string): Observable<void> {
    return this.http.post<void>(`${this.api}/${groupId}/members/${userId}/reject`, {});
  }

  setRole(groupId: string, userId: string, role: MemberRole): Observable<GroupMember> {
    return this.http.post<GroupMember>(`${this.api}/${groupId}/members/${userId}/role`, { role });
  }

  removeMember(groupId: string, userId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/${groupId}/members/${userId}`);
  }

  // ── Invitations ───────────────────────────────────────────────
  invitations(): Observable<Invitation[]> {
    return this.http.get<Invitation[]>(`${this.api}/invitations`);
  }

  invite(groupId: string, userId: string): Observable<GroupMember> {
    return this.http.post<GroupMember>(`${this.api}/${groupId}/invite/${userId}`, {});
  }

  acceptInvite(groupId: string): Observable<Group> {
    return this.http.post<Group>(`${this.api}/${groupId}/invitation/accept`, {});
  }

  declineInvite(groupId: string): Observable<void> {
    return this.http.post<void>(`${this.api}/${groupId}/invitation/decline`, {});
  }

  // ── Community posts ───────────────────────────────────────────
  posts(groupId: string, page = 1, size = 20): Observable<GroupPost[]> {
    return this.http.get<GroupPost[]>(`${this.api}/${groupId}/posts`, { params: { page, size } });
  }

  createPost(groupId: string, post: { content: string; content_html?: string | null; image_ids?: string[] }): Observable<GroupPost> {
    return this.http.post<GroupPost>(`${this.api}/${groupId}/posts`, post);
  }

  deletePost(postId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/posts/${postId}`);
  }

  likePost(postId: string): Observable<void> {
    return this.http.put<void>(`${this.api}/posts/${postId}/like`, {});
  }

  unlikePost(postId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/posts/${postId}/like`);
  }

  comments(postId: string): Observable<GroupComment[]> {
    return this.http.get<GroupComment[]>(`${this.api}/posts/${postId}/comments`);
  }

  addComment(postId: string, body: string): Observable<GroupComment> {
    return this.http.post<GroupComment>(`${this.api}/posts/${postId}/comments`, { body });
  }

  deleteComment(commentId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/comments/${commentId}`);
  }
}

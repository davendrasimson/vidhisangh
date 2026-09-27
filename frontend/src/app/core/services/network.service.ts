import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  Comment,
  Connection,
  ConnectionStatus,
  DirectoryPerson,
  FeedItem,
  LinkPreview,
  PostCreate,
  PublicProfile,
  ReactionType,
  TrendingTag,
} from '@core/models/network.models';

@Injectable({ providedIn: 'root' })
export class NetworkService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/network`;

  // ── Feed & posts ──────────────────────────────────────────────
  feed(page = 1, size = 20): Observable<FeedItem[]> {
    return this.http.get<FeedItem[]>(`${this.api}/feed`, { params: { page, size } });
  }

  createPost(payload: PostCreate): Observable<FeedItem> {
    return this.http.post<FeedItem>(`${this.api}/posts`, payload);
  }

  /** Resolve a URL's Open Graph preview (feed 'unfurl'). 404 when none found. */
  linkPreview(url: string): Observable<LinkPreview> {
    return this.http.get<LinkPreview>(`${this.api}/link-preview`, { params: { url } });
  }

  deletePost(postId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/posts/${postId}`);
  }

  share(postId: string, content = ''): Observable<FeedItem> {
    return this.http.post<FeedItem>(`${this.api}/posts/${postId}/share`, { content });
  }

  // ── Reactions ─────────────────────────────────────────────────
  react(postId: string, reaction: ReactionType): Observable<void> {
    return this.http.put<void>(`${this.api}/posts/${postId}/reaction`, { reaction });
  }

  unreact(postId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/posts/${postId}/reaction`);
  }

  // ── Bookmarks ─────────────────────────────────────────────────
  bookmark(postId: string): Observable<void> {
    return this.http.put<void>(`${this.api}/posts/${postId}/bookmark`, {});
  }

  unbookmark(postId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/posts/${postId}/bookmark`);
  }

  bookmarks(page = 1, size = 20): Observable<FeedItem[]> {
    return this.http.get<FeedItem[]>(`${this.api}/bookmarks`, { params: { page, size } });
  }

  trending(limit = 8): Observable<TrendingTag[]> {
    return this.http.get<TrendingTag[]>(`${this.api}/trending`, { params: { limit } });
  }

  mentions(page = 1, size = 20): Observable<FeedItem[]> {
    return this.http.get<FeedItem[]>(`${this.api}/mentions`, { params: { page, size } });
  }

  // ── Comments ──────────────────────────────────────────────────
  comments(postId: string): Observable<Comment[]> {
    return this.http.get<Comment[]>(`${this.api}/posts/${postId}/comments`);
  }

  addComment(postId: string, body: string): Observable<Comment> {
    return this.http.post<Comment>(`${this.api}/posts/${postId}/comments`, { body });
  }

  // ── Directory & graph ─────────────────────────────────────────
  directory(page = 1, size = 30): Observable<DirectoryPerson[]> {
    return this.http.get<DirectoryPerson[]>(`${this.api}/directory`, { params: { page, size } });
  }

  person(userId: string): Observable<PublicProfile> {
    return this.http.get<PublicProfile>(`${this.api}/people/${userId}`);
  }

  userPosts(userId: string, page = 1, size = 20): Observable<FeedItem[]> {
    return this.http.get<FeedItem[]>(`${this.api}/users/${userId}/posts`, { params: { page, size } });
  }

  connect(userId: string, message?: string): Observable<Connection> {
    return this.http.post<Connection>(`${this.api}/connections/${userId}`, { message });
  }

  acceptConnection(connectionId: string): Observable<Connection> {
    return this.http.post<Connection>(`${this.api}/connections/${connectionId}/accept`, {});
  }

  declineConnection(connectionId: string): Observable<Connection> {
    return this.http.post<Connection>(`${this.api}/connections/${connectionId}/decline`, {});
  }

  connections(status?: ConnectionStatus): Observable<Connection[]> {
    const params: Record<string, string> = status ? { status } : {};
    return this.http.get<Connection[]>(`${this.api}/connections`, { params });
  }

  incomingRequests(): Observable<Connection[]> {
    return this.http.get<Connection[]>(`${this.api}/connections/requests`);
  }

  follow(userId: string): Observable<void> {
    return this.http.put<void>(`${this.api}/follow/${userId}`, {});
  }

  unfollow(userId: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/follow/${userId}`);
  }
}

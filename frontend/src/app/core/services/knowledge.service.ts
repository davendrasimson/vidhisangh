import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  KnowledgeCategory,
  KnowledgeCreate,
  KnowledgeItem,
  KnowledgeSummary,
} from '@core/models/knowledge.models';

@Injectable({ providedIn: 'root' })
export class KnowledgeService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/knowledge`;

  list(filters: { category?: KnowledgeCategory | ''; q?: string; practice_area?: string; page?: number; size?: number } = {}): Observable<KnowledgeSummary[]> {
    const params: Record<string, string> = {};
    params['page'] = String(filters.page ?? 1);
    params['size'] = String(filters.size ?? 50);
    if (filters.category) params['category'] = filters.category;
    if (filters.q) params['q'] = filters.q;
    if (filters.practice_area) params['practice_area'] = filters.practice_area;
    return this.http.get<KnowledgeSummary[]>(`${this.api}/items`, { params });
  }

  get(id: string): Observable<KnowledgeItem> {
    return this.http.get<KnowledgeItem>(`${this.api}/items/${id}`);
  }

  create(payload: KnowledgeCreate): Observable<KnowledgeItem> {
    return this.http.post<KnowledgeItem>(`${this.api}/items`, payload);
  }

  update(id: string, payload: KnowledgeCreate): Observable<KnowledgeItem> {
    return this.http.patch<KnowledgeItem>(`${this.api}/items/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/items/${id}`);
  }
}

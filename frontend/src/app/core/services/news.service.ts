import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import { NewsCategory, NewsItem, NewsItemCreate } from '@core/models/news.models';

@Injectable({ providedIn: 'root' })
export class NewsService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/news`;

  list(filters: { q?: string; category?: NewsCategory | ''; source?: string; page?: number; size?: number } = {}): Observable<NewsItem[]> {
    const params: Record<string, string> = {};
    if (filters.q) params['q'] = filters.q;
    if (filters.category) params['category'] = filters.category;
    if (filters.source) params['source'] = filters.source;
    if (filters.page) params['page'] = String(filters.page);
    if (filters.size) params['size'] = String(filters.size);
    return this.http.get<NewsItem[]>(this.api, { params });
  }

  create(payload: NewsItemCreate): Observable<NewsItem> {
    return this.http.post<NewsItem>(this.api, payload);
  }
}

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  Listing,
  ListingCreate,
  ListingResponse,
  ListingType,
} from '@core/models/marketplace.models';

@Injectable({ providedIn: 'root' })
export class MarketplaceService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/marketplace`;

  browse(filters: { type?: ListingType | ''; q?: string } = {}): Observable<Listing[]> {
    const params: Record<string, string> = {};
    if (filters.type) params['type'] = filters.type;
    if (filters.q) params['q'] = filters.q;
    return this.http.get<Listing[]>(`${this.api}/listings`, { params });
  }

  mine(): Observable<Listing[]> {
    return this.http.get<Listing[]>(`${this.api}/listings/mine`);
  }

  create(payload: ListingCreate): Observable<Listing> {
    return this.http.post<Listing>(`${this.api}/listings`, payload);
  }

  close(id: string): Observable<Listing> {
    return this.http.post<Listing>(`${this.api}/listings/${id}/close`, {});
  }

  respond(id: string, message: string): Observable<ListingResponse> {
    return this.http.post<ListingResponse>(`${this.api}/listings/${id}/respond`, { message });
  }

  responses(id: string): Observable<ListingResponse[]> {
    return this.http.get<ListingResponse[]>(`${this.api}/listings/${id}/responses`);
  }

  accept(id: string, responseId: string): Observable<Listing> {
    return this.http.post<Listing>(`${this.api}/listings/${id}/responses/${responseId}/accept`, {});
  }
}

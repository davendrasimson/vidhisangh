import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';

export interface SampleDataStatus {
  available: boolean;
  counts: Record<string, number>;
}

@Injectable({ providedIn: 'root' })
export class SampleDataService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/sample-data`;

  status(): Observable<SampleDataStatus> {
    return this.http.get<SampleDataStatus>(this.api);
  }

  create(): Observable<SampleDataStatus> {
    return this.http.post<SampleDataStatus>(this.api, {});
  }

  clear(): Observable<SampleDataStatus> {
    return this.http.post<SampleDataStatus>(`${this.api}/delete`, { confirmed: true });
  }
}

import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { environment } from '@env/environment';
import { Tenant } from '@core/models/auth.models';

/** Current organisation (tenant) context. */
@Injectable({ providedIn: 'root' })
export class TenantService {
  private readonly http = inject(HttpClient);
  private readonly api = environment.apiBaseUrl;

  readonly current = signal<Tenant | null>(null);

  load(): Observable<Tenant> {
    return this.http
      .get<Tenant>(`${this.api}/tenants/current`)
      .pipe(tap((t) => this.current.set(t)));
  }
}

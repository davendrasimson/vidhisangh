import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '@env/environment';
import {
  CaseRead,
  CitationGraph,
  CitationRelationship,
  CiteCheckReport,
  Judgment,
  JudgmentCreate,
  SearchFacets,
  SearchFilters,
  SearchPage,
} from '@core/models/research.models';

@Injectable({ providedIn: 'root' })
export class ResearchService {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiBaseUrl}/research`;

  /** One page of ranked results plus the total match count. */
  search(filters: SearchFilters, page = 1, size = 20): Observable<SearchPage> {
    const params = this.params(filters).set('page', page).set('size', size);
    return this.http.get<SearchPage>(`${this.api}/judgments`, { params });
  }

  /** Counts by court / year / case type / judge / outcome for the same filters. */
  facets(filters: SearchFilters): Observable<SearchFacets> {
    return this.http.get<SearchFacets>(`${this.api}/judgments/facets`, {
      params: this.params(filters),
    });
  }

  get(id: string): Observable<Judgment> {
    return this.http.get<Judgment>(`${this.api}/judgments/${id}`);
  }

  /** A case (CNR) with every order the library holds for it, oldest first. */
  case(cnr: string): Observable<CaseRead> {
    return this.http.get<CaseRead>(`${this.api}/cases/${encodeURIComponent(cnr)}`);
  }

  add(payload: JudgmentCreate): Observable<Judgment> {
    return this.http.post<Judgment>(`${this.api}/judgments`, payload);
  }

  citations(id: string): Observable<CitationGraph> {
    return this.http.get<CitationGraph>(`${this.api}/judgments/${id}/citations`);
  }

  addCitation(
    id: string,
    body: { to_judgment_id?: string; external_citation?: string; relationship_type: CitationRelationship },
  ): Observable<{ id: string }> {
    return this.http.post<{ id: string }>(`${this.api}/judgments/${id}/citations`, body);
  }

  /** Every case citation in a draft, verified against the library. Nothing is stored. */
  citeCheck(text: string): Observable<CiteCheckReport> {
    return this.http.post<CiteCheckReport>(`${this.api}/cite-check`, { text });
  }

  /** The same for a Word (.docx) file — body, tables, footnotes and endnotes. */
  citeCheckUpload(file: File): Observable<CiteCheckReport> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post<CiteCheckReport>(`${this.api}/cite-check/upload`, form);
  }

  /** Only send what is set — the API treats absent and empty the same, but the
   *  URL stays readable and cache keys stay stable. */
  private params(f: SearchFilters): HttpParams {
    let p = new HttpParams();
    const put = (k: string, v: string | number | null | undefined) => {
      if (v !== undefined && v !== null && v !== '') p = p.set(k, v);
    };
    put('q', f.q?.trim());
    put('court_level', f.court_level);
    put('court', f.court);
    put('case_type', f.case_type);
    put('case_year', f.case_year);
    put('judge', f.judge);
    put('advocate', f.advocate);
    put('outcome', f.outcome);
    put('act', f.act);
    put('section', f.section);
    put('year_from', f.year_from);
    put('year_to', f.year_to);
    return p;
  }
}

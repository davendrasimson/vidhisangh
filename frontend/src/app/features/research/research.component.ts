import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { ResearchService } from '@core/services/research.service';
import { NotificationService } from '@core/services/notification.service';
import {
  CourtLevel,
  FacetBucket,
  FacetKey,
  JudgmentCreate,
  Judgment,
  JudgmentSummary,
  SearchFacets,
  SearchFilters,
} from '@core/models/research.models';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';
import { SnippetPipe } from '@shared/pipes/snippet.pipe';
import { DatePipe } from '@angular/common';
import { ResearchFolder, ResearchWorkspaceService, SavedAuthority } from './research-workspace.service';

import { publicOrigin } from '@core/platform/platform';
import { saveBlob } from '@core/platform/save-file';
const csv = (v: string): string[] => v.split(',').map((s) => s.trim()).filter(Boolean);
const PAGE_SIZE = 20;

interface ActiveFilter {
  key: FacetKey;
  label: string;
  value: string;
}

interface LegalIssueSuggestion { label: string; act: string; section: string; query: string; reason: string; }

const ISSUE_RULES: { terms: string[]; suggestion: LegalIssueSuggestion }[] = [
  { terms: ['cheque', 'bounce', 'dishonour'], suggestion: { label: 'Cheque dishonour', act: 'Negotiable Instruments Act, 1881', section: '138', query: 'cheque dishonour legally enforceable debt notice', reason: 'Potential NI Act section 138 issue; dates of presentation, return, notice and complaint are material.' } },
  { terms: ['fraud', 'cheat', 'money', 'deceived'], suggestion: { label: 'Cheating', act: 'Bharatiya Nyaya Sanhita, 2023', section: '318', query: 'cheating dishonest inducement delivery property', reason: 'The facts may raise cheating or civil breach questions; intention at inception is commonly material.' } },
  { terms: ['anticipatory bail', 'arrest', 'false case'], suggestion: { label: 'Anticipatory bail', act: 'Bharatiya Nagarik Suraksha Sanhita, 2023', section: '482', query: 'anticipatory bail arrest accusation', reason: 'Potential pre-arrest bail issue under BNSS section 482.' } },
  { terms: ['fir', 'police refused', 'cognizable'], suggestion: { label: 'Registration of FIR', act: 'Bharatiya Nagarik Suraksha Sanhita, 2023', section: '173', query: 'registration FIR cognizable offence police', reason: 'Potential information in cognizable cases issue under BNSS section 173.' } },
  { terms: ['electronic', 'whatsapp', 'email', 'cctv', 'recording'], suggestion: { label: 'Electronic evidence', act: 'Bharatiya Sakshya Adhiniyam, 2023', section: '63', query: 'electronic record admissibility certificate', reason: 'Electronic-record proof and authenticity requirements may apply.' } },
  { terms: ['contract', 'agreement', 'breach', 'payment'], suggestion: { label: 'Contractual breach', act: 'Indian Contract Act, 1872', section: '73', query: 'breach contract damages compensation', reason: 'Potential compensation for breach; causation, remoteness and mitigation may be relevant.' } },
  { terms: ['delay', 'limitation', 'late filing'], suggestion: { label: 'Limitation and delay', act: 'Limitation Act, 1963', section: '5', query: 'condonation delay sufficient cause limitation', reason: 'A limitation calculation and any available exclusion or condonation require date-specific checking.' } },
];

@Component({
  selector: 'app-research',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, SnippetPipe, VsDateInputComponent, NgTemplateOutlet, FormsModule, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './research.component.html',
  styleUrl: './research.component.scss',
})
export class ResearchComponent implements OnInit {
  private readonly research = inject(ResearchService);
  private readonly notify = inject(NotificationService);
  protected readonly workspace = inject(ResearchWorkspaceService);

  // ── Query state ────────────────────────────────────────────────
  protected query = '';
  protected readonly filters = signal<SearchFilters>({});
  protected readonly results = signal<JudgmentSummary[]>([]);
  protected readonly total = signal(0);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly totalIsEstimate = signal(false);

  /** From a result card's "N orders in this case" chip to the case timeline. */
  protected openCase(cnr: string | null): void {
    if (cnr) void this.router.navigate(['/app/research/case', cnr]);
  }
  protected readonly totalIsLowerBound = signal(false);
  protected readonly ranked = signal(true);
  protected readonly recentYears = signal<number | null>(null);
  protected readonly page = signal(1);
  protected readonly facets = signal<SearchFacets | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadingMore = signal(false);
  protected readonly view = signal<'results' | 'workspace' | 'compare' | 'alerts'>('results');
  protected readonly factsMode = signal(false);
  protected readonly advancedOpen = signal(false);
  protected readonly compareLoading = signal(false);
  protected readonly comparedJudgments = signal<Judgment[]>([]);
  protected folderName = '';
  protected alertName = '';
  protected readonly facetsLoading = signal(false);
  /** Size of the whole corpus, learned from the first unfiltered facet call. */
  protected readonly corpusSize = signal<number | null>(null);

  protected readonly hasMore = computed(() => this.results().length < this.total());
  protected issueSuggestions(): LegalIssueSuggestion[] {
    if (!this.factsMode() || this.query.trim().length < 8) return [];
    const text = this.query.toLocaleLowerCase('en-IN');
    return ISSUE_RULES.filter((rule) => rule.terms.some((term) => text.includes(term))).map((rule) => rule.suggestion).slice(0, 4);
  }
  protected readonly leadingMatches = computed(() => this.results().filter((item) => item.citation).slice(0, 3));
  protected readonly recentMatches = computed(() => [...this.results()].filter((item) => item.judgment_date).sort((a, b) => (b.judgment_date ?? '').localeCompare(a.judgment_date ?? '')).slice(0, 3));

  protected readonly activeFilters = computed<ActiveFilter[]>(() => {
    const f = this.filters();
    const out: ActiveFilter[] = [];
    if (f.court) out.push({ key: 'court', label: 'Court', value: f.court });
    if (f.case_year) out.push({ key: 'case_year', label: 'Year', value: String(f.case_year) });
    if (f.case_type) out.push({ key: 'case_type', label: 'Type', value: f.case_type });
    if (f.judge) out.push({ key: 'judge', label: 'Judge', value: f.judge });
    if (f.advocate) out.push({ key: 'advocate', label: 'Advocate', value: f.advocate });
    if (f.outcome) out.push({ key: 'outcome', label: 'Outcome', value: f.outcome });
    return out;
  });

  // ── Add-judgment panel (secondary) ─────────────────────────────
  protected readonly showAdd = signal(false);
  protected readonly saving = signal(false);
  protected addForm = this.blankAdd();

  protected readonly courtLevels: { value: CourtLevel; label: string }[] = [
    { value: 'supreme_court', label: 'Supreme Court' },
    { value: 'high_court', label: 'High Court' },
    { value: 'tribunal', label: 'Tribunal' },
    { value: 'district', label: 'District Court' },
    { value: 'other', label: 'Other' },
  ];

  async ngOnInit(): Promise<void> {
    // Deep links from a case or judgment page: /app/research?advocate=…&judge=…
    const qp = this.route.snapshot.queryParamMap;
    const seed: SearchFilters = {};
    for (const key of ['q', 'court', 'case_type', 'judge', 'advocate', 'outcome', 'act', 'section'] as const) {
      const v = qp.get(key);
      if (v) seed[key] = v;
    }
    if (qp.get('case_year')) seed.case_year = Number(qp.get('case_year'));
    if (Object.keys(seed).length) {
      this.query = seed.q ?? '';
      this.filters.set(seed);
    }
    await this.runSearch();
    void this.checkAlerts();
  }

  // ── Searching ──────────────────────────────────────────────────
  protected async submit(): Promise<void> {
    this.filters.update((f) => ({ ...f, q: this.query.trim() }));
    await this.runSearch();
  }

  protected async applyIssue(issue: LegalIssueSuggestion): Promise<void> {
    this.query = issue.query;
    this.filters.set({ q: issue.query, act: issue.act, section: issue.section });
    this.view.set('results');
    await this.runSearch();
  }

  protected async setTopFilter(key: 'court_level' | 'year_from' | 'year_to', value: string): Promise<void> {
    const next = { ...this.filters() };
    if (!value) delete next[key];
    else if (key === 'court_level') next.court_level = value as CourtLevel;
    else next[key] = Number(value);
    this.filters.set(next);
    await this.runSearch();
  }

  protected async clearAll(): Promise<void> {
    this.query = '';
    this.filters.set({});
    await this.runSearch();
  }

  /** Click a facet value to narrow; click the active one again to widen. */
  protected async toggle(key: FacetKey, value: string): Promise<void> {
    const current = this.filters();
    const same = String(current[key] ?? '') === value;
    const next: SearchFilters = { ...current };
    if (same) {
      delete next[key];
    } else if (key === 'case_year') {
      next.case_year = Number(value);
    } else {
      next[key] = value;
    }
    this.filters.set(next);
    await this.runSearch();
  }

  protected isActive(key: FacetKey, value: string): boolean {
    return String(this.filters()[key] ?? '') === value;
  }

  protected saveAuthority(event: MouseEvent, judgment: JudgmentSummary): void {
    event.preventDefault(); event.stopPropagation(); this.workspace.saveAuthority(judgment);
  }

  protected toggleCompare(event: MouseEvent, judgmentId: string): void {
    event.preventDefault(); event.stopPropagation(); this.workspace.toggleCompare(judgmentId);
  }

  protected isCompared(judgmentId: string): boolean { return this.workspace.state().compareIds.includes(judgmentId); }

  protected async openCompare(): Promise<void> {
    this.view.set('compare');
    const ids = this.workspace.state().compareIds;
    if (!ids.length) { this.comparedJudgments.set([]); return; }
    this.compareLoading.set(true);
    try { this.comparedJudgments.set(await Promise.all(ids.map((id) => firstValueFrom(this.research.get(id))))); }
    finally { this.compareLoading.set(false); }
  }

  protected createFolder(): void {
    if (this.workspace.createFolder(this.folderName)) this.folderName = '';
  }

  protected folderNameFor(id: string): string { return this.workspace.state().folders.find((folder) => folder.id === id)?.name ?? 'Unfiled'; }
  protected workspaceFolders(): ResearchFolder[] { return [{ id: '', name: 'Unfiled authorities', createdAt: '' }, ...this.workspace.state().folders]; }
  protected folderEmpty(folderId: string): boolean { return !this.workspace.state().authorities.some((item) => item.folderId === folderId); }

  protected updateSaved(item: SavedAuthority, key: 'folderId' | 'note', value: string): void { this.workspace.updateAuthority(item.id, { [key]: value }); }

  protected createAlert(): void {
    const name = this.alertName.trim() || this.query.trim() || this.activeFilters().map((item) => item.value).join(' · ');
    if (!name || (!this.filters().q && !this.activeFilters().length && !this.filters().act && !this.filters().section)) {
      this.notify.error('Run a search or choose filters before creating an alert.'); return;
    }
    this.workspace.addAlert(name, this.filters(), this.results()[0]?.id ?? null); this.alertName = '';
  }

  protected runAlert(filters: SearchFilters, alertId?: string): void {
    this.query = filters.q ?? ''; this.filters.set({ ...filters }); this.view.set('results');
    void this.runSearch().then(() => { if (alertId) this.workspace.recordAlertCheck(alertId, this.results()[0]?.id ?? null, true); });
  }

  protected exportMemo(): void {
    const state = this.workspace.state();
    const lines = ['# Research memorandum', '', `Generated ${new Date().toLocaleString('en-IN')}`, ''];
    for (const folder of [{ id: '', name: 'Unfiled authorities' }, ...state.folders]) {
      const items = state.authorities.filter((item) => item.folderId === folder.id);
      if (!items.length) continue;
      lines.push(`## ${folder.name}`, '');
      for (const [index, item] of items.entries()) lines.push(`${index + 1}. **${item.title}**${item.citation ? ` — ${item.citation}` : ''}`, `   ${item.court}${item.judgmentDate ? ` · ${item.judgmentDate}` : ''}`, item.note ? `   Note: ${item.note}` : '', `   ${publicOrigin()}/app/research/${item.judgmentId}`, '');
    }
    const blob = new Blob([lines.filter((line) => line !== undefined).join('\n')], { type: 'text/markdown;charset=utf-8' });
    void saveBlob(blob, `research-memo-${new Date().toISOString().slice(0, 10)}.md`);
  }

  private async checkAlerts(): Promise<void> {
    for (const alert of this.workspace.state().alerts.filter((item) => item.enabled).slice(0, 10)) {
      try {
        const page = await firstValueFrom(this.research.search(alert.filters, 1, 1));
        this.workspace.recordAlertCheck(alert.id, page.items[0]?.id ?? null);
      } catch { /* the main research page remains usable if a background alert check fails */ }
    }
  }

  protected async loadMore(): Promise<void> {
    if (this.loadingMore() || !this.hasMore()) return;
    this.loadingMore.set(true);
    try {
      const next = this.page() + 1;
      const pageResult = await firstValueFrom(
        this.research.search(this.filters(), next, PAGE_SIZE),
      );
      this.results.update((r) => [...r, ...pageResult.items]);
      this.page.set(next);
    } catch {
      /* surfaced by the interceptor */
    } finally {
      this.loadingMore.set(false);
    }
  }

  private async runSearch(): Promise<void> {
    this.loading.set(true);
    this.facetsLoading.set(true);
    this.page.set(1);
    const f = this.filters();
    // Results and facets are independent requests; don't make the list wait
    // on five GROUP BYs over the corpus.
    const resultsReq = firstValueFrom(this.research.search(f, 1, PAGE_SIZE));
    const facetsReq = firstValueFrom(this.research.facets(f));
    try {
      const pageResult = await resultsReq;
      this.results.set(pageResult.items);
      this.total.set(pageResult.total);
      this.totalIsEstimate.set(pageResult.total_is_estimate);
      this.totalIsLowerBound.set(pageResult.total_is_lower_bound);
      this.ranked.set(pageResult.ranked);
      this.recentYears.set(pageResult.recent_years);
    } catch {
      this.results.set([]);
      this.total.set(0);
    } finally {
      this.loading.set(false);
    }
    try {
      const facets = await facetsReq;
      this.facets.set(facets);
      if (!f.q && this.activeFilters().length === 0) this.corpusSize.set(facets.total);
    } catch {
      this.facets.set(null);
    } finally {
      this.facetsLoading.set(false);
    }
  }

  // ── Display helpers ────────────────────────────────────────────
  /** "CRM-M 33310/2019" — the registry number as a practitioner writes it. */
  protected caseLabel(j: JudgmentSummary): string | null {
    if (!j.case_type) return null;
    const num = j.case_number ? ` ${j.case_number}` : '';
    const year = j.case_year ? `/${j.case_year}` : '';
    return `${j.case_type}${num}${year}`;
  }

  protected title(j: JudgmentSummary): string {
    return j.cause_title || j.case_name;
  }

  protected judgesLine(j: JudgmentSummary): string | null {
    if (!j.judge_names?.length) return null;
    const shown = j.judge_names.slice(0, 3).map((n) => `Justice ${n}`);
    const extra = j.judge_names.length - shown.length;
    return shown.join(', ') + (extra > 0 ? ` +${extra}` : '');
  }

  protected courtLabel(level: CourtLevel): string {
    return this.courtLevels.find((c) => c.value === level)?.label ?? level;
  }

  protected compact(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)} million`;
    if (n >= 10_000) return `${Math.round(n / 1000)}k`;
    return n.toLocaleString('en-IN');
  }

  /** Facet lists are short; keep them stable-keyed for @for. */
  protected trackBucket(_: number, b: FacetBucket): string {
    return b.value;
  }

  // ── Add judgment ───────────────────────────────────────────────
  protected async submitAdd(): Promise<void> {
    const f = this.addForm;
    if (!f.case_name.trim() || !f.citation.trim() || !f.court.trim() || this.saving()) return;
    this.saving.set(true);
    try {
      const payload: JudgmentCreate = {
        case_name: f.case_name.trim(),
        citation: f.citation.trim(),
        court: f.court.trim(),
        court_level: f.court_level,
        judges: csv(f.judges),
        acts: csv(f.acts),
        sections: csv(f.sections),
        keywords: csv(f.keywords),
        judgment_date: f.judgment_date || null,
        headnote: f.headnote.trim() || null,
        outcome: f.outcome.trim() || null,
      };
      const created = await firstValueFrom(this.research.add(payload));
      this.notify.success(`Added ${created.case_name}.`);
      this.addForm = this.blankAdd();
      this.showAdd.set(false);
      this.results.update((l) => [{ ...created }, ...l]);
      this.total.update((t) => t + 1);
    } catch {
      /* surfaced by the interceptor (e.g. duplicate citation) */
    } finally {
      this.saving.set(false);
    }
  }

  private blankAdd() {
    return {
      case_name: '', citation: '', court: '', court_level: 'supreme_court' as CourtLevel,
      judges: '', acts: '', sections: '', keywords: '', judgment_date: '', headnote: '', outcome: '',
    };
  }
}

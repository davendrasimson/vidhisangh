import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { ACTS, ACTS_EDITION, CRIMINAL_TRANSITION_SOURCE, LEGAL_GLOSSARY, ActGuide } from './data/acts';
import { matchesAct, rankActs } from './knowledge.helpers';
import { KnowledgeBookmarks } from './knowledge-bookmarks.service';
import { firstValueFrom } from 'rxjs';

interface StatutePassage {
  actId: string;
  section: string;
  text: string;
}

interface StatuteSearchResult extends StatutePassage {
  act: ActGuide;
  score: number;
}

@Component({
  selector: 'app-acts-library', standalone: true,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './acts-library.component.html',
  styleUrl: './acts-library.component.scss',
})
export class ActsLibraryComponent {
  protected readonly bookmarks = inject(KnowledgeBookmarks);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly http = inject(HttpClient);
  protected readonly acts = ACTS;
  protected readonly edition = ACTS_EDITION;
  protected readonly transitionSource = CRIMINAL_TRANSITION_SOURCE;
  protected readonly glossary = LEGAL_GLOSSARY;
  protected readonly areas = [...new Set(ACTS.map((a) => a.area))];
  protected readonly query = signal('');
  protected readonly statuteQuery = signal('');
  protected readonly exactPhrase = signal(true);
  protected readonly statuteSearching = signal(false);
  protected readonly statuteSearchError = signal(false);
  protected readonly statuteSearched = signal(false);
  protected readonly statuteResults = signal<StatuteSearchResult[]>([]);
  protected readonly situation = signal('');
  protected readonly searchingSituation = signal(false);
  protected readonly area = signal('');
  protected readonly savedOnly = signal(false);
  protected readonly selected = signal<ActGuide | null>(null);
  protected readonly visible = computed(() => ACTS.filter((a) =>
    (!this.area() || a.area === this.area()) && matchesAct(a, this.query()) &&
    (!this.savedOnly() || this.bookmarks.has(`act:${a.id}`))));
  protected readonly related = computed(() => ACTS.filter((a) => this.selected()?.related.includes(a.id)));
  protected readonly topics = ['Police complaint', 'Cheque bounce', 'Delayed flat', 'Refund', 'Start a company', 'Free lawyer'];
  protected readonly recommendations = computed(() => rankActs(this.situation(), ACTS).slice(0, 6));
  private statuteIndex: StatutePassage[] | null = null;

  constructor() {
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      this.selected.set(ACTS.find((a) => a.id === params.get('act')) ?? null);
      // ?q= from the home screen's search: run the statutory search straight away.
      const q = params.get('q')?.trim() ?? '';
      if (q.length >= 2 && q !== this.statuteQuery()) {
        this.statuteQuery.set(q);
        void this.searchStatutoryText();
      }
    });
  }

  protected select(act: ActGuide | null): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { act: act?.id ?? null }, queryParamsHandling: 'merge' });
    document.getElementById('knowledge-content')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  protected topic(value: string): void {
    this.area.set(''); this.savedOnly.set(false); this.query.set(value);
  }

  protected findApplicableLaws(): void {
    this.searchingSituation.set(true);
    document.getElementById('law-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  protected clearSituation(): void {
    this.situation.set('');
    this.searchingSituation.set(false);
  }

  protected async searchStatutoryText(): Promise<void> {
    const query = this.statuteQuery().trim();
    if (query.length < 2 || this.statuteSearching()) return;
    this.statuteSearching.set(true);
    this.statuteSearchError.set(false);
    this.statuteSearched.set(true);
    try {
      this.statuteIndex ??= await firstValueFrom(this.http.get<StatutePassage[]>('/bare-acts/text/search-index.json?edition=2026-09-26-text-2'));
      const normalized = query.replace(/^["“]|["”]$/g, '').trim().toLocaleLowerCase('en-IN');
      const sectionLookup = normalized.match(/^(?:section|sec\.?|s\.?)?\s*(\d{1,3}[a-z]{0,2})$/i)?.[1]?.toUpperCase();
      const terms = normalized.split(/\s+/).filter((term) => term.length > 1);
      const acts = new Map(ACTS.map((act) => [act.id, act]));
      const matches: StatuteSearchResult[] = [];
      for (const passage of this.statuteIndex) {
        const text = passage.text.toLocaleLowerCase('en-IN');
        const exactAt = text.indexOf(normalized);
        const termHits = terms.reduce((count, term) => count + (text.includes(term) ? 1 : 0), 0);
        const sectionMatch = !!sectionLookup && passage.section.toUpperCase() === sectionLookup;
        const qualifies = this.exactPhrase() ? exactAt >= 0 || sectionMatch : termHits === terms.length || sectionMatch;
        const act = acts.get(passage.actId);
        if (!qualifies || !act) continue;
        matches.push({ ...passage, act, score: (sectionMatch ? 200 : 0) + (exactAt >= 0 ? 100 : 0) + termHits });
      }
      this.statuteResults.set(matches.sort((a, b) => b.score - a.score || a.act.title.localeCompare(b.act.title)).slice(0, 75));
      setTimeout(() => document.getElementById('statute-results')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
    } catch {
      this.statuteResults.set([]);
      this.statuteSearchError.set(true);
    } finally {
      this.statuteSearching.set(false);
    }
  }

  protected searchSegments(text: string): { text: string; match: boolean }[] {
    const query = this.statuteQuery().trim().replace(/^["“]|["”]$/g, '');
    if (!query) return [{ text, match: false }];
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return text.split(new RegExp(`(${escaped})`, 'gi')).filter(Boolean)
      .map((part) => ({ text: part, match: part.toLocaleLowerCase('en-IN') === query.toLocaleLowerCase('en-IN') }));
  }
}

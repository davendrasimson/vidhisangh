import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ACTS } from './data/acts';
import { CRIMINAL_LAW_COMPARISON_SOURCE, SectionCrossReference, sectionCrossReferences } from './data/section-intelligence';
import { displayDate, lawApplicability, lawVersionProfile } from './data/law-versions';
import { ResearchService } from '@core/services/research.service';
import { MattersService } from '@core/services/matters.service';
import { NotificationService } from '@core/services/notification.service';
import { AuthService } from '@core/auth/auth.service';
import { JudgmentSummary } from '@core/models/research.models';
import { Matter } from '@core/models/matters.models';
import { firstValueFrom } from 'rxjs';
import { isNativeApp } from '@core/platform/platform';
import { saveBlob } from '@core/platform/save-file';

const BARE_ACTS_EDITION = '2026-09-26-text-2';

type ReaderMode = 'text' | 'pdf';
type BlockKind = 'chapter' | 'section' | 'heading' | 'body';

interface ReaderBlock {
  id: number;
  text: string;
  kind: BlockKind;
}

interface TextSegment {
  text: string;
  match: boolean;
}

interface SectionEntry {
  blockId: number;
  reference: string;
  title: string;
}

@Component({
  selector: 'app-act-reader',
  standalone: true,
  imports: [FormsModule, RouterLink, MatButtonModule, MatIconModule],
  templateUrl: './act-reader.component.html',
  styleUrl: './act-reader.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ActReaderComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly research = inject(ResearchService);
  private readonly matters = inject(MattersService);
  private readonly notify = inject(NotificationService);
  protected readonly auth = inject(AuthService);
  protected readonly acts = ACTS;
  protected readonly comparisonSource = CRIMINAL_LAW_COMPARISON_SOURCE;
  protected readonly snapshotDate = '27 September 2026';
  protected readonly snapshotIsoDate = '2026-09-27';
  protected readonly selectedIndex = signal(0);
  protected readonly search = signal('');
  protected readonly shelfOpen = signal(true);
  protected readonly readerMode = signal<ReaderMode>('text');
  protected readonly textLoading = signal(true);
  protected readonly textError = signal(false);
  protected readonly actText = signal('');
  protected readonly textQuery = signal('');
  protected readonly activeMatch = signal(0);
  protected readonly fontSize = signal(17);
  protected readonly copied = signal(false);
  protected readonly sectionSelection = signal('');
  protected readonly intelligenceOpen = signal(false);
  protected readonly applicableOn = signal(this.snapshotIsoDate);
  protected readonly authorities = signal<JudgmentSummary[]>([]);
  protected readonly authorityTotal = signal(0);
  protected readonly authorityLoading = signal(false);
  protected readonly authorityError = signal(false);
  protected readonly matterList = signal<Matter[]>([]);
  protected readonly matterLoading = signal(false);
  protected readonly matterError = signal(false);
  protected readonly selectedMatterId = signal('');
  protected readonly savingToMatter = signal(false);
  protected readonly comparisonLoading = signal(false);
  protected readonly comparisonError = signal(false);
  protected readonly comparison = signal<{ actId: string; section: string; text: string } | null>(null);
  protected readonly pdfLoading = signal(true);
  protected readonly selected = computed(() => this.acts[this.selectedIndex()]);
  protected readonly filteredActs = computed(() => {
    const query = this.search().trim().toLowerCase();
    return query ? this.acts.filter((act) => `${act.short} ${act.title} ${act.area}`.toLowerCase().includes(query)) : this.acts;
  });
  protected readonly localPdfUrl = computed(
    () => `/bare-acts/${this.selected().id}.pdf?edition=${BARE_ACTS_EDITION}`,
  );
  protected readonly readerSource = computed(() => this.sanitizer.bypassSecurityTrustResourceUrl(
    `${this.localPdfUrl()}#page=1&view=FitH&toolbar=1`,
  ));
  protected readonly currentNumber = computed(() => this.selectedIndex() + 1);
  /** Android's WebView cannot render a PDF in a frame, so the app opens the
   *  bundled copy in the phone's own PDF viewer (via the share sheet) instead. */
  protected readonly native = isNativeApp();
  protected async openPdfInApp(): Promise<void> {
    try {
      const blob = await firstValueFrom(this.http.get(this.localPdfUrl(), { responseType: 'blob' }));
      await saveBlob(blob, `${this.selected().short || this.selected().id}.pdf`);
    } catch {
      this.notify.error('Could not open the PDF.');
    }
  }
  protected readonly textBlocks = computed<ReaderBlock[]>(() => {
    const title = this.selected().title.toLowerCase();
    return this.actText().split(/\n{2,}/)
      .map((text) => text.trim())
      .filter((text, index) => text && !(index === 0 && text.toLowerCase() === title))
      .map((text, id) => ({ id, text, kind: this.blockKind(text) }));
  });
  protected readonly matchingBlocks = computed(() => {
    const query = this.textQuery().trim().toLocaleLowerCase('en-IN');
    if (!query) return [];
    return this.textBlocks()
      .filter((block) => block.text.toLocaleLowerCase('en-IN').includes(query))
      .map((block) => block.id);
  });
  protected readonly sectionEntries = computed<SectionEntry[]>(() => this.textBlocks().flatMap((block) => {
    const match = block.text.match(/^(\d+[A-Z]{0,2})\.\s*([^\n]{0,110})/i);
    if (!match) return [];
    return [{ blockId: block.id, reference: match[1], title: match[2].replace(/[.—-].*$/, '').trim() || `Section ${match[1]}` }];
  }));
  protected readonly activeSection = computed<SectionEntry | null>(() => {
    const chosen = Number(this.sectionSelection());
    if (this.sectionSelection() && Number.isFinite(chosen)) {
      const direct = this.sectionEntries().find((entry) => entry.blockId === chosen);
      if (direct) return direct;
    }
    const matchId = this.matchingBlocks()[this.activeMatch()];
    if (matchId !== undefined) return [...this.sectionEntries()].reverse().find((entry) => entry.blockId <= matchId) ?? null;
    return this.sectionEntries()[0] ?? null;
  });
  protected readonly crossReferences = computed(() => {
    const section = this.activeSection();
    return section ? sectionCrossReferences(this.selected().id, section.reference) : [];
  });
  protected readonly versionProfile = computed(() => lawVersionProfile(this.selected().id));
  protected readonly applicability = computed(() => lawApplicability(this.selected().id, this.applicableOn(), this.activeSection()?.reference ?? ''));
  protected readonly wordCount = computed(() => this.actText().trim() ? this.actText().trim().split(/\s+/).length : 0);

  constructor() {
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      const requested = params.get('act');
      const index = this.acts.findIndex((act) => act.id === requested);
      this.selectedIndex.set(index >= 0 ? index : 0);
      this.readerMode.set('text');
      this.textQuery.set(params.get('q')?.trim().replace(/^["“]|["”]$/g, '') ?? '');
      this.sectionSelection.set(params.get('section')?.trim() ?? '');
      this.activeMatch.set(0);
      this.loadText(this.selected().id, params.get('section')?.trim() ?? '');
    });
  }

  protected choose(id: string): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { act: id }, queryParamsHandling: 'merge' });
    if (matchMedia('(max-width: 760px)').matches) this.shelfOpen.set(false);
  }

  protected move(offset: number): void {
    const next = Math.min(this.acts.length - 1, Math.max(0, this.selectedIndex() + offset));
    this.choose(this.acts[next].id);
  }

  protected showPdf(): void {
    this.pdfLoading.set(true);
    this.readerMode.set('pdf');
  }

  protected updateTextQuery(value: string): void {
    this.textQuery.set(value);
    this.activeMatch.set(0);
    if (value.trim()) setTimeout(() => this.scrollToMatch(0));
  }

  protected jumpMatch(offset: number): void {
    const matches = this.matchingBlocks();
    if (!matches.length) return;
    const next = (this.activeMatch() + offset + matches.length) % matches.length;
    this.activeMatch.set(next);
    this.scrollToMatch(next);
    if (this.intelligenceOpen()) void this.loadAuthorities();
  }

  protected isActiveMatch(blockId: number): boolean {
    return this.matchingBlocks()[this.activeMatch()] === blockId;
  }

  protected segments(text: string): TextSegment[] {
    const query = this.textQuery().trim();
    if (!query) return [{ text, match: false }];
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return text.split(new RegExp(`(${escaped})`, 'gi')).filter(Boolean)
      .map((part) => ({ text: part, match: part.toLocaleLowerCase('en-IN') === query.toLocaleLowerCase('en-IN') }));
  }

  protected async copyText(): Promise<void> {
    await navigator.clipboard.writeText(this.actText());
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1600);
  }

  protected async copyProvision(): Promise<void> {
    const matches = this.matchingBlocks();
    const startId = matches.length ? matches[this.activeMatch()] : Number(this.sectionSelection());
    if (!Number.isFinite(startId)) return;
    const provision = this.provisionText(startId);
    if (!provision) return;
    await navigator.clipboard.writeText(`${this.selected().title}\n\n${provision}\n\nOfficial source: ${this.selected().source}`);
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1600);
  }

  protected jumpToSection(blockId: string): void {
    this.sectionSelection.set(blockId);
    const id = Number(blockId);
    if (Number.isFinite(id)) setTimeout(() => document.getElementById(`act-text-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    if (this.intelligenceOpen()) void this.loadAuthorities();
  }

  protected setApplicableOn(value: string): void {
    if (value) this.applicableOn.set(value);
  }

  protected formatLegalDate(value: string): string {
    return displayDate(value);
  }

  protected async toggleIntelligence(): Promise<void> {
    this.intelligenceOpen.update((open) => !open);
    if (!this.intelligenceOpen()) return;
    if (!this.sectionSelection() && this.sectionEntries().length) this.sectionSelection.set(String(this.sectionEntries()[0].blockId));
    await Promise.all([this.loadAuthorities(), this.loadMatters()]);
  }

  protected async loadAuthorities(): Promise<void> {
    const section = this.activeSection();
    if (!section || !this.auth.hasPermission('research:use')) return;
    const requestKey = `${this.selected().id}:${section.reference}`;
    this.authorityLoading.set(true);
    this.authorityError.set(false);
    try {
      const result = await firstValueFrom(this.research.search({ act: this.selected().title, section: section.reference }, 1, 6));
      if (`${this.selected().id}:${this.activeSection()?.reference}` !== requestKey) return;
      this.authorities.set(result.items);
      this.authorityTotal.set(result.total);
    } catch {
      this.authorities.set([]);
      this.authorityTotal.set(0);
      this.authorityError.set(true);
    } finally {
      if (`${this.selected().id}:${this.activeSection()?.reference}` === requestKey) this.authorityLoading.set(false);
    }
  }

  protected async loadMatters(): Promise<void> {
    if (!this.auth.hasPermission('matter:read') || this.matterList().length || this.matterLoading()) return;
    this.matterLoading.set(true);
    this.matterError.set(false);
    try {
      const matters: Matter[] = [];
      for (let page = 1; ; page++) {
        const batch = await firstValueFrom(this.matters.list(undefined, page, 50));
        matters.push(...batch);
        if (batch.length < 50) break;
      }
      this.matterList.set(matters.filter((matter) => matter.status !== 'closed'));
    } catch {
      this.matterError.set(true);
    } finally {
      this.matterLoading.set(false);
    }
  }

  protected async saveProvisionToMatter(): Promise<void> {
    const matterId = this.selectedMatterId();
    const section = this.activeSection();
    if (!matterId || !section || this.savingToMatter()) return;
    const provision = this.provisionText(section.blockId);
    if (!provision) return;
    this.savingToMatter.set(true);
    try {
      await firstValueFrom(this.matters.addAuthority(matterId, {
        kind: 'statute', judgment_id: null, act_id: this.selected().id,
        reference: `${this.selected().title} · Section ${section.reference}`,
        paragraph_no: null, quotation: provision,
        proposition: `${this.applicability().label}: ${this.applicability().headline}`,
        stance: 'pending_review', source_url: this.selected().source,
      }));
      this.notify.success(`Section ${section.reference} pinned to the matter research binder.`);
    } catch {
      this.notify.error('The provision could not be saved to the matter.');
    } finally {
      this.savingToMatter.set(false);
    }
  }

  protected authorityTitle(judgment: JudgmentSummary): string {
    return judgment.cause_title || judgment.case_name;
  }

  protected actLabel(id: string): string {
    return this.acts.find((act) => act.id === id)?.short ?? id.toUpperCase();
  }

  protected provisionTextForView(blockId: number): string {
    return this.provisionText(blockId);
  }

  protected async compareReference(reference: SectionCrossReference): Promise<void> {
    this.comparisonLoading.set(true);
    this.comparisonError.set(false);
    this.comparison.set(null);
    try {
      const text = await firstValueFrom(this.http.get(`/bare-acts/text/${reference.correspondingActId}.txt?edition=${BARE_ACTS_EDITION}`, { responseType: 'text' }));
      const provision = this.extractProvision(text, reference.correspondingSection);
      if (!provision) throw new Error('Provision not found');
      this.comparison.set({ actId: reference.correspondingActId, section: reference.correspondingSection, text: provision });
    } catch {
      this.comparisonError.set(true);
    } finally {
      this.comparisonLoading.set(false);
    }
  }

  private loadText(id: string, requestedSection = ''): void {
    this.textLoading.set(true);
    this.textError.set(false);
    this.actText.set('');
    this.http.get(`/bare-acts/text/${id}.txt?edition=${BARE_ACTS_EDITION}`, { responseType: 'text' })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (text) => {
          if (this.selected().id !== id) return;
          this.actText.set(text);
          this.textLoading.set(false);
          setTimeout(() => {
            if (this.matchingBlocks().length) {
              this.scrollToMatch(0);
              return;
            }
            const section = requestedSection.toUpperCase().replace(/\(.*/, '').replace(/[–-].*/, '');
            const match = section ? this.sectionEntries().find((entry) => entry.reference.toUpperCase() === section) : null;
            if (match) {
              this.sectionSelection.set(String(match.blockId));
              document.getElementById(`act-text-${match.blockId}`)?.scrollIntoView({ block: 'start' });
            } else {
              if (!this.sectionSelection() && this.sectionEntries().length) this.sectionSelection.set(String(this.sectionEntries()[0].blockId));
              document.querySelector('.manual-scroll')?.scrollTo({ top: 0 });
            }
            if (this.intelligenceOpen()) void this.loadAuthorities();
          });
        },
        error: () => {
          if (this.selected().id !== id) return;
          this.textLoading.set(false);
          this.textError.set(true);
        },
      });
  }

  private scrollToMatch(matchIndex: number): void {
    const blockId = this.matchingBlocks()[matchIndex];
    setTimeout(() => document.getElementById(`act-text-${blockId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  }

  private provisionText(blockId: number): string {
    const blocks = this.textBlocks();
    let startIndex = blocks.findIndex((block) => block.id === blockId);
    if (startIndex < 0) return '';
    while (startIndex > 0 && blocks[startIndex].kind !== 'section') startIndex--;
    let endIndex = startIndex + 1;
    while (endIndex < blocks.length && blocks[endIndex].kind !== 'section' && blocks[endIndex].kind !== 'chapter') endIndex++;
    return blocks.slice(startIndex, endIndex).map((block) => block.text).join('\n\n');
  }

  private extractProvision(text: string, section: string): string {
    const base = section.toUpperCase().replace(/^SECTION\s*/, '').replace(/\(.*/, '').replace(/[–-].*/, '');
    const escaped = base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const startPattern = new RegExp(`(?:^|\\n|\\s)${escaped}\\.\\s*(?=[A-Z\"“(\[])`, 'gm');
    const matches = [...text.matchAll(startPattern)];
    const lower = text.toLocaleLowerCase('en-IN');
    const enactedAt = Math.max(lower.indexOf('be it enacted'), lower.indexOf('it is enacted as follows'));
    const candidates = enactedAt >= 0 ? matches.filter((item) => (item.index ?? 0) > enactedAt) : matches;
    let match = candidates[0];
    if (candidates[1] && ((candidates[1].index ?? 0) - (match?.index ?? 0) < 500 || enactedAt < 0)) match = candidates[1];
    if (!match) return '';
    const start = match.index + (match[0].length - match[0].trimStart().length);
    const rest = text.slice(start + 1);
    const next = /(?:\n|\s)\d{1,3}[A-Z]{0,2}\.\s*(?=[A-Z\"“(\[])/m.exec(rest);
    const end = next ? start + 1 + next.index : Math.min(text.length, start + 12000);
    return text.slice(start, end).trim();
  }

  private blockKind(text: string): BlockKind {
    if (/^(CHAPTER|PART|SCHEDULE|APPENDIX)\b/i.test(text)) return 'chapter';
    if (/^\d+[A-Z]?[.]\s/.test(text)) return 'section';
    if (text.length < 130 && text === text.toUpperCase() && /[A-Z]/.test(text)) return 'heading';
    return 'body';
  }
}

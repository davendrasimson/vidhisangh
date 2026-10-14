import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { ResearchService } from '@core/services/research.service';
import { MattersService } from '@core/services/matters.service';
import { AuthService } from '@core/auth/auth.service';
import { NotificationService } from '@core/services/notification.service';
import { TellAFriendService } from '@core/services/tell-a-friend.service';
import { publicOrigin } from '@core/platform/platform';
import { CitationGraph, CitationRelationship, Judgment } from '@core/models/research.models';
import { Matter } from '@core/models/matters.models';
import { DatePipe } from '@angular/common';

@Component({
  selector: 'app-judgment-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './judgment-detail.component.html',
  styleUrl: './judgment-detail.component.scss',
})
export class JudgmentDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly research = inject(ResearchService);
  private readonly matters = inject(MattersService);
  private readonly notify = inject(NotificationService);
  private readonly sharing = inject(TellAFriendService);
  protected readonly auth = inject(AuthService);

  private id = '';
  protected readonly judgment = signal<Judgment | null>(null);
  protected readonly graph = signal<CitationGraph | null>(null);
  protected readonly loading = signal(true);
  protected readonly readerOpen = signal(false);
  protected readonly readerQuery = signal('');
  protected readonly activeMatch = signal(0);
  protected readonly selectedParagraph = signal<number | null>(null);
  protected readonly fontSize = signal(16);
  protected readonly matterList = signal<Matter[]>([]);
  protected readonly selectedMatterId = signal('');
  protected readonly matterLoading = signal(false);
  protected readonly savingExcerpt = signal(false);
  protected readonly paragraphs = computed(() => this.toParagraphs(this.judgment()?.full_text ?? ''));
  protected readonly matchingParagraphs = computed(() => {
    const query = this.readerQuery().trim().toLocaleLowerCase('en-IN');
    if (!query) return [];
    return this.paragraphs().filter((paragraph) => paragraph.text.toLocaleLowerCase('en-IN').includes(query)).map((paragraph) => paragraph.number);
  });
  protected readonly treatmentSummary = computed(() => {
    const edges = [...(this.graph()?.cites ?? []), ...(this.graph()?.cited_by ?? [])];
    return this.relationships.map((relationship) => ({ relationship, count: edges.filter((edge) => edge.relationship_type === relationship).length })).filter((item) => item.count);
  });

  protected readonly relationships: CitationRelationship[] = [
    'followed', 'overruled', 'distinguished', 'referred', 'relied_on', 'dissented',
  ];
  protected citeForm = { citation: '', relationship_type: 'followed' as CitationRelationship };

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => {
      const id = p.get('id');
      if (id) {
        this.id = id;
        void this.load();
      }
    });
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [judgment, graph] = await Promise.all([
        firstValueFrom(this.research.get(this.id)),
        firstValueFrom(this.research.citations(this.id)),
      ]);
      this.judgment.set(judgment);
      this.graph.set(graph);
      const paragraph = Number(this.route.snapshot.queryParamMap.get('para'));
      if (Number.isFinite(paragraph) && paragraph > 0) {
        this.readerOpen.set(true);
        this.selectedParagraph.set(paragraph);
        setTimeout(() => this.scrollToParagraph(paragraph));
      }
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected label(rel: CitationRelationship): string {
    return rel.replace('_', ' ');
  }

  protected openReader(): void {
    this.readerOpen.set(true);
    if (this.selectedParagraph() === null && this.paragraphs().length) this.selectedParagraph.set(1);
    setTimeout(() => document.querySelector('.judgment-reader')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }

  protected updateReaderQuery(value: string): void {
    this.readerQuery.set(value);
    this.activeMatch.set(0);
    if (value.trim()) setTimeout(() => this.scrollToParagraph(this.matchingParagraphs()[0]));
  }

  protected jumpMatch(offset: number): void {
    const matches = this.matchingParagraphs();
    if (!matches.length) return;
    const next = (this.activeMatch() + offset + matches.length) % matches.length;
    this.activeMatch.set(next);
    this.selectParagraph(matches[next]);
  }

  protected selectParagraph(number: number): void {
    this.selectedParagraph.set(number);
    void this.router.navigate([], { relativeTo: this.route, queryParams: { para: number }, queryParamsHandling: 'merge', replaceUrl: true });
    this.scrollToParagraph(number);
  }

  protected paragraphSegments(text: string): { text: string; match: boolean }[] {
    const query = this.readerQuery().trim();
    if (!query) return [{ text, match: false }];
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return text.split(new RegExp(`(${escaped})`, 'gi')).filter(Boolean).map((part) => ({
      text: part,
      match: part.toLocaleLowerCase('en-IN') === query.toLocaleLowerCase('en-IN'),
    }));
  }

  protected citationLine(): string {
    const judgment = this.judgment();
    if (!judgment) return '';
    const title = judgment.cause_title || judgment.case_name;
    const citation = judgment.neutral_citation || judgment.citation || judgment.cnr_number || '';
    const date = judgment.judgment_date ? `, decided ${judgment.judgment_date}` : '';
    return `${title}${citation ? `, ${citation}` : ''} (${judgment.court}${date})`;
  }

  /** The headnote's public page, readable without an account (served by the API at /judgments/). */
  protected shareHeadnote(j: Judgment): Promise<void> {
    const summary = j.ai_headnote?.summary ?? '';
    return this.sharing.shareLink(
      j.case_name,
      `${j.case_name}: ${summary}\n\nAI-generated headnote, free on VidhiSangh:`,
      `${publicOrigin()}/judgments/${j.id}/`,
      'Share headnote',
    );
  }

  protected async copyCitation(): Promise<void> {
    await navigator.clipboard.writeText(this.citationLine());
    this.notify.success('Citation copied.');
  }

  protected async copyParagraph(number: number): Promise<void> {
    const paragraph = this.paragraphs().find((item) => item.number === number);
    if (!paragraph) return;
    await navigator.clipboard.writeText(`${this.citationLine()}, para ${number}\n\n${paragraph.text}\n\nSource: ${location.href}`);
    this.notify.success(`Paragraph ${number} copied with citation.`);
  }

  protected async loadMatters(): Promise<void> {
    if (this.matterList().length || this.matterLoading() || !this.auth.hasPermission('matter:read')) return;
    this.matterLoading.set(true);
    try {
      const matters: Matter[] = [];
      for (let page = 1; ; page++) {
        const batch = await firstValueFrom(this.matters.list(undefined, page, 50));
        matters.push(...batch);
        if (batch.length < 50) break;
      }
      this.matterList.set(matters.filter((matter) => matter.status !== 'closed'));
    } finally {
      this.matterLoading.set(false);
    }
  }

  protected async saveParagraphToMatter(): Promise<void> {
    const matterId = this.selectedMatterId();
    const number = this.selectedParagraph();
    const paragraph = this.paragraphs().find((item) => item.number === number);
    if (!matterId || !paragraph || this.savingExcerpt()) return;
    this.savingExcerpt.set(true);
    try {
      await firstValueFrom(this.matters.addAuthority(matterId, {
        kind: 'judgment', judgment_id: this.id, act_id: null,
        reference: this.citationLine(), paragraph_no: paragraph.number,
        quotation: paragraph.text, proposition: null, stance: 'pending_review',
        source_url: this.judgment()?.url || location.href,
      }));
      this.notify.success(`Paragraph ${paragraph.number} pinned to the matter research binder.`);
    } finally {
      this.savingExcerpt.set(false);
    }
  }

  protected async addCitation(): Promise<void> {
    const citation = this.citeForm.citation.trim();
    if (!citation) return;
    try {
      await firstValueFrom(
        this.research.addCitation(this.id, {
          external_citation: citation,
          relationship_type: this.citeForm.relationship_type,
        }),
      );
      this.citeForm = { citation: '', relationship_type: 'followed' };
      this.graph.set(await firstValueFrom(this.research.citations(this.id)));
      this.notify.success('Citation recorded.');
    } catch {
      /* handled */
    }
  }

  private scrollToParagraph(number: number | undefined): void {
    if (!number) return;
    setTimeout(() => document.getElementById(`judgment-para-${number}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  }

  private toParagraphs(fullText: string): { number: number; text: string }[] {
    if (!fullText.trim()) return [];
    let blocks = fullText.split(/\n\s*\n+/).map((text) => text.replace(/\s*\n\s*/g, ' ').replace(/\s{2,}/g, ' ').trim()).filter(Boolean);
    if (blocks.length < 4) blocks = fullText.split(/\n+/).map((text) => text.replace(/\s{2,}/g, ' ').trim()).filter((text) => text.length > 1);
    return blocks.map((text, index) => ({ number: index + 1, text }));
  }
}

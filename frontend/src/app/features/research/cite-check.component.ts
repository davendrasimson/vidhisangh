import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { ResearchService } from '@core/services/research.service';
import { NotificationService } from '@core/services/notification.service';
import { CiteCheckFinding, CiteCheckReport, CiteCheckStatus } from '@core/models/research.models';
import { saveBlob } from '@core/platform/save-file';

interface StatusMeta { label: string; icon: string; tone: 'success' | 'warning' | 'danger' | 'muted'; help: string; }

/** Display order: what needs attention first. */
const STATUS_ORDER: CiteCheckStatus[] = ['not_found', 'possible_matches', 'cited_elsewhere', 'matched_by_name', 'verified'];

export const STATUS_META: Record<CiteCheckStatus, StatusMeta> = {
  verified: { label: 'Verified', icon: 'verified', tone: 'success', help: 'The library holds this very record (SCR, INSC or neutral citation).' },
  matched_by_name: { label: 'Matched by name', icon: 'person_search', tone: 'success', help: 'The library does not key cases by this reporter; the case you named, decided in that year window, was found.' },
  possible_matches: { label: 'Several possible matches', icon: 'help_center', tone: 'warning', help: 'More than one record fits the names and year — pick the right one yourself.' },
  cited_elsewhere: { label: 'Cited by other judgments', icon: 'format_quote', tone: 'warning', help: 'No record of its own, but other judgments in the library cite this string, so the authority exists.' },
  not_found: { label: 'Not found — verify', icon: 'report', tone: 'danger', help: 'Nothing in the library holds or cites this citation. Check it against the reporter before filing; a mistyped or invented citation looks exactly like this.' },
};

/**
 * Cite check — paste a draft (or upload a .docx) and every case citation in it is
 * found and verified against the research library. Deterministic, no AI: it says
 * whether an authority exists, never whether it supports the proposition.
 */
@Component({
  selector: 'app-cite-check',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './cite-check.component.html',
})
export class CiteCheckComponent {
  private readonly research = inject(ResearchService);
  private readonly notify = inject(NotificationService);

  protected text = '';
  protected readonly fileName = signal<string | null>(null);
  protected readonly checking = signal(false);
  protected readonly report = signal<CiteCheckReport | null>(null);
  protected readonly filter = signal<CiteCheckStatus | 'all'>('all');
  protected readonly meta = STATUS_META;
  protected readonly statuses = STATUS_ORDER;

  protected readonly findings = computed<CiteCheckFinding[]>(() => {
    const r = this.report();
    if (!r) return [];
    const f = this.filter();
    const rows = f === 'all' ? r.findings : r.findings.filter((x) => x.status === f);
    return [...rows].sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status));
  });

  /** Citations that need a human look before filing. */
  protected readonly attention = computed(() => {
    const c = this.report()?.counts ?? {};
    return (c.not_found ?? 0) + (c.possible_matches ?? 0) + (c.cited_elsewhere ?? 0);
  });

  protected count(status: CiteCheckStatus): number {
    return this.report()?.counts[status] ?? 0;
  }

  protected async check(): Promise<void> {
    const text = this.text.trim();
    if (!text) { this.notify.error('Paste the text of your draft first, or upload a Word file.'); return; }
    this.checking.set(true);
    try {
      this.report.set(await firstValueFrom(this.research.citeCheck(text)));
      this.fileName.set(null);
      this.filter.set('all');
    } catch { /* handled by the HTTP error interceptor */ } finally { this.checking.set(false); }
  }

  protected async onFile(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.checking.set(true);
    try {
      this.report.set(await firstValueFrom(this.research.citeCheckUpload(file)));
      this.fileName.set(file.name);
      this.text = '';
      this.filter.set('all');
    } catch { /* handled */ } finally { this.checking.set(false); }
  }

  protected reset(): void {
    this.report.set(null);
    this.fileName.set(null);
    this.text = '';
  }

  /** The report as a spreadsheet — one row per distinct citation. */
  protected downloadCsv(): void {
    const r = this.report();
    if (!r) return;
    const cell = (v: unknown): string => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const head = ['Citation', 'Reporter', 'Status', 'Case as cited', 'Occurrences', 'Matched case', 'Library citation', 'Court', 'Decided', 'Cited in (judgments)', 'Warnings'];
    const lines = r.findings.map((f) => [
      f.citation, f.reporter, STATUS_META[f.status].label, f.case_name_as_cited, f.occurrences,
      f.judgment?.case_name, f.judgment?.citation ?? f.judgment?.neutral_citation, f.judgment?.court,
      f.judgment?.judgment_date ? new Date(f.judgment.judgment_date).toLocaleDateString('en-IN') : '',
      f.cited_in_count, f.warnings.join(' | '),
    ].map(cell).join(','));
    const csv = [head.map(cell).join(','), ...lines].join('\r\n');
    void saveBlob(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }), `cite-check-${r.checked_at.slice(0, 10)}.csv`);
  }
}

import { Injectable, computed, inject, signal } from '@angular/core';
import { AuthService } from '@core/auth/auth.service';
import { JudgmentSummary, SearchFilters } from '@core/models/research.models';
import { NotificationService } from '@core/services/notification.service';

export interface SavedAuthority {
  id: string;
  judgmentId: string;
  title: string;
  citation: string | null;
  court: string;
  judgmentDate: string | null;
  folderId: string;
  note: string;
  savedAt: string;
  /** The AI headnote's one-paragraph summary at the time of saving (Supreme Court judgments that have one). */
  aiSummary?: string | null;
}

export interface ResearchFolder { id: string; name: string; createdAt: string; }

export interface ResearchAlert {
  id: string;
  name: string;
  filters: SearchFilters;
  enabled: boolean;
  createdAt: string;
  lastCheckedAt: string;
  lastSeenJudgmentId: string | null;
  newCount: number;
}

interface WorkspaceState {
  folders: ResearchFolder[];
  authorities: SavedAuthority[];
  alerts: ResearchAlert[];
  compareIds: string[];
}

const EMPTY: WorkspaceState = { folders: [], authorities: [], alerts: [], compareIds: [] };

@Injectable({ providedIn: 'root' })
export class ResearchWorkspaceService {
  private readonly auth = inject(AuthService);
  private readonly notify = inject(NotificationService);
  private readonly revision = signal(0);
  readonly state = computed(() => { this.revision(); return this.read(); });

  private key(): string {
    const user = this.auth.user();
    return `vs-research-workspace:${user?.tenant_id}:${user?.id}`;
  }

  private read(): WorkspaceState {
    try {
      const parsed = JSON.parse(localStorage.getItem(this.key()) ?? 'null') as Partial<WorkspaceState> | null;
      return parsed ? {
        folders: Array.isArray(parsed.folders) ? parsed.folders : [],
        authorities: Array.isArray(parsed.authorities) ? parsed.authorities : [],
        alerts: Array.isArray(parsed.alerts) ? parsed.alerts : [],
        compareIds: Array.isArray(parsed.compareIds) ? parsed.compareIds.slice(0, 2) : [],
      } : { ...EMPTY };
    } catch { return { ...EMPTY }; }
  }

  private write(state: WorkspaceState): void {
    try {
      localStorage.setItem(this.key(), JSON.stringify(state));
      this.revision.update((value) => value + 1);
    } catch { this.notify.error('The research workspace could not be saved in this browser.'); }
  }

  createFolder(name: string): string | null {
    const clean = name.trim();
    if (!clean) return null;
    const state = this.read();
    const existing = state.folders.find((folder) => folder.name.toLocaleLowerCase('en-IN') === clean.toLocaleLowerCase('en-IN'));
    if (existing) return existing.id;
    const id = crypto.randomUUID();
    this.write({ ...state, folders: [...state.folders, { id, name: clean, createdAt: new Date().toISOString() }] });
    return id;
  }

  saveAuthority(judgment: JudgmentSummary, folderId = ''): void {
    const state = this.read();
    if (state.authorities.some((item) => item.judgmentId === judgment.id)) {
      this.notify.success('This authority is already in the workspace.');
      return;
    }
    const item: SavedAuthority = {
      id: crypto.randomUUID(), judgmentId: judgment.id, title: judgment.cause_title || judgment.case_name,
      citation: judgment.citation, court: judgment.court, judgmentDate: judgment.judgment_date,
      folderId, note: '', savedAt: new Date().toISOString(), aiSummary: judgment.ai_summary ?? null,
    };
    this.write({ ...state, authorities: [item, ...state.authorities] });
    this.notify.success('Authority saved to the research workspace.');
  }

  removeAuthority(id: string): void {
    const state = this.read();
    this.write({ ...state, authorities: state.authorities.filter((item) => item.id !== id) });
  }

  updateAuthority(id: string, changes: Partial<Pick<SavedAuthority, 'folderId' | 'note'>>): void {
    const state = this.read();
    this.write({ ...state, authorities: state.authorities.map((item) => item.id === id ? { ...item, ...changes } : item) });
  }

  toggleCompare(judgmentId: string): void {
    const state = this.read();
    const selected = state.compareIds.includes(judgmentId)
      ? state.compareIds.filter((id) => id !== judgmentId)
      : [...state.compareIds.filter((id) => id !== judgmentId), judgmentId].slice(-2);
    this.write({ ...state, compareIds: selected });
  }

  clearCompare(): void { this.write({ ...this.read(), compareIds: [] }); }

  addAlert(name: string, filters: SearchFilters, latestJudgmentId: string | null = null): void {
    const clean = name.trim();
    if (!clean) return;
    const state = this.read();
    const now = new Date().toISOString();
    const alert: ResearchAlert = { id: crypto.randomUUID(), name: clean, filters: { ...filters }, enabled: true, createdAt: now, lastCheckedAt: now, lastSeenJudgmentId: latestJudgmentId, newCount: 0 };
    this.write({ ...state, alerts: [alert, ...state.alerts] });
    this.notify.success('Research alert saved.');
  }

  toggleAlert(id: string): void {
    const state = this.read();
    this.write({ ...state, alerts: state.alerts.map((item) => item.id === id ? { ...item, enabled: !item.enabled } : item) });
  }

  recordAlertCheck(id: string, latestJudgmentId: string | null, opened = false): void {
    const state = this.read();
    this.write({ ...state, alerts: state.alerts.map((item) => {
      if (item.id !== id) return item;
      const changed = !!latestJudgmentId && !!item.lastSeenJudgmentId && latestJudgmentId !== item.lastSeenJudgmentId;
      return { ...item, lastCheckedAt: new Date().toISOString(), lastSeenJudgmentId: opened ? latestJudgmentId : item.lastSeenJudgmentId || latestJudgmentId, newCount: opened ? 0 : changed ? Math.max(item.newCount || 0, 1) : item.newCount || 0 };
    }) });
  }

  removeAlert(id: string): void {
    const state = this.read();
    this.write({ ...state, alerts: state.alerts.filter((item) => item.id !== id) });
  }
}

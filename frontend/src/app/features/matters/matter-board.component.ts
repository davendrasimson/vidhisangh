import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { CdkDragDrop, DragDropModule } from '@angular/cdk/drag-drop';
import { AuthService } from '@core/auth/auth.service';
import { MattersService } from '@core/services/matters.service';
import { NotificationService } from '@core/services/notification.service';
import { BoardCard, BoardColumn, BoardFlag, MatterBoard, MatterStage } from '@core/models/matters.models';

/** A board column: a stage, or (in the owner view) one person's matters. */
export interface Lane { key: string; label: string; count: number; matters: BoardCard[]; stage: MatterStage | null; }

interface FlagMeta { label: string; icon: string; tone: 'danger' | 'warning' | 'muted'; }

export const FLAG_META: Record<BoardFlag, FlagMeta> = {
  hearing_today: { label: 'Hearing today', icon: 'today', tone: 'danger' },
  limitation_passed: { label: 'Limitation passed', icon: 'event_busy', tone: 'danger' },
  limitation_soon: { label: 'Limitation within 30 days', icon: 'hourglass_bottom', tone: 'danger' },
  overdue_task: { label: 'Overdue task', icon: 'assignment_late', tone: 'danger' },
  hearing_soon: { label: 'Hearing within 7 days', icon: 'event_upcoming', tone: 'warning' },
  no_next_step: { label: 'No next step', icon: 'help_outline', tone: 'warning' },
  stale: { label: 'Nothing for 30 days', icon: 'bedtime', tone: 'warning' },
  on_hold: { label: 'On hold', icon: 'pause_circle', tone: 'muted' },
};

const FLAG_ORDER: BoardFlag[] = ['hearing_today', 'limitation_passed', 'limitation_soon', 'overdue_task', 'hearing_soon', 'no_next_step', 'stale', 'on_hold'];

export const STAGE_LABEL: Record<MatterStage, string> = {
  intake: 'Intake', filing: 'Filing', pleadings: 'Pleadings', evidence: 'Evidence',
  arguments: 'Arguments', judgment: 'Judgment', closed: 'Closed',
};

/**
 * The matter board: every matter that is not closed, one column per stage, each
 * card with its owner, next hearing, next task and what needs a person's attention.
 * Read-only over the matters, hearings and tasks you already keep — nothing to maintain.
 */
@Component({
  selector: 'app-matter-board',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, MatIconModule, MatButtonModule, DragDropModule],
  templateUrl: './matter-board.component.html',
})
export class MatterBoardComponent implements OnInit {
  private readonly matters = inject(MattersService);
  protected readonly auth = inject(AuthService);

  protected readonly board = signal<MatterBoard | null>(null);
  protected readonly loading = signal(true);
  protected readonly mineOnly = signal(false);
  protected readonly flagFilter = signal<BoardFlag | 'attention' | 'all'>('all');
  protected readonly meta = FLAG_META;
  protected readonly stageLabel = STAGE_LABEL;
  protected readonly flagOrder = FLAG_ORDER;

  private readonly notify = inject(NotificationService);
  /** Columns are stages (drag a card to move it) or owners (one lane per person). */
  protected readonly lane = signal<'stage' | 'owner'>('stage');

  /** Lanes with the flag filter applied; empty stage columns stay so the stages read left to right. */
  protected readonly lanes = computed<Lane[]>(() => {
    const b = this.board();
    if (!b) return [];
    const f = this.flagFilter();
    const keep = (c: BoardCard) => f === 'all' ? true
      : f === 'attention' ? c.flags.some((x) => x !== 'hearing_soon' && x !== 'on_hold')
      : c.flags.includes(f);
    if (this.lane() === 'stage') {
      return b.columns.map((col: BoardColumn) => {
        const matters = col.matters.filter(keep);
        return { key: col.stage, label: STAGE_LABEL[col.stage], count: matters.length, matters, stage: col.stage };
      });
    }
    const byOwner = new Map<string, Lane>();
    for (const col of b.columns) {
      for (const c of col.matters.filter(keep)) {
        const key = c.owner_id ?? 'unassigned';
        const owner = byOwner.get(key) ?? { key, label: c.owner_name ?? 'No owner', count: 0, matters: [], stage: null };
        owner.matters.push(c); owner.count++;
        byOwner.set(key, owner);
      }
    }
    return [...byOwner.values()].sort((x, y) => x.key === 'unassigned' ? 1 : y.key === 'unassigned' ? -1 : y.count - x.count || x.label.localeCompare(y.label));
  });

  protected readonly shown = computed(() => this.lanes().reduce((n, c) => n + c.count, 0));

  /** A card dropped on another stage column: move it there and save the stage (PATCH /matters/{id}). */
  protected async onDrop(event: CdkDragDrop<Lane>): Promise<void> {
    const card = event.item.data as BoardCard;
    const to = event.container.data, from = event.previousContainer.data;
    const b = this.board();
    if (!b || !to.stage || to.stage === from.stage) return;
    const stage = to.stage;
    this.board.set({
      ...b,
      columns: b.columns.map((col) => {
        const matters = col.stage === from.stage ? col.matters.filter((m) => m.id !== card.id)
          : col.stage === stage ? [...col.matters, { ...card, stage }] : col.matters;
        return { ...col, matters, count: matters.length };
      }),
    });
    try {
      await firstValueFrom(this.matters.update(card.id, { stage }));
      this.notify.success(`${card.title} moved to ${STAGE_LABEL[stage]}.`);
    } catch {
      this.notify.error('Could not change the stage; the board was reloaded.');
      await this.load();
    }
  }

  protected flagCount(flag: BoardFlag): number {
    return this.board()?.flag_counts[flag] ?? 0;
  }

  ngOnInit(): void {
    void this.load();
  }

  protected async toggleMine(): Promise<void> {
    this.mineOnly.update((v) => !v);
    await this.load();
  }

  protected setFlag(flag: BoardFlag | 'attention' | 'all'): void {
    this.flagFilter.set(this.flagFilter() === flag ? 'all' : flag);
  }

  protected async load(): Promise<void> {
    this.loading.set(true);
    try {
      const userId = this.mineOnly() ? this.auth.user()?.id : undefined;
      this.board.set(await firstValueFrom(this.matters.board(userId)));
    } catch { /* handled by the HTTP error interceptor */ } finally { this.loading.set(false); }
  }

  /** Days from today, for "in 3 days" / "today" / "2 days ago". */
  protected daysUntil(iso: string | null): number | null {
    if (!iso) return null;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
    return Math.round((new Date(y, m - 1, d).getTime() - today.getTime()) / 86_400_000);
  }

  protected relative(iso: string | null): string {
    const n = this.daysUntil(iso);
    if (n === null) return '';
    if (n === 0) return 'today';
    if (n === 1) return 'tomorrow';
    if (n === -1) return 'yesterday';
    return n > 0 ? `in ${n} days` : `${-n} days ago`;
  }
}

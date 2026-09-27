import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { CalendarService } from '@core/services/calendar.service';
import { NotificationService } from '@core/services/notification.service';
import { AgendaItem, EventType } from '@core/models/calendar.models';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';

interface DayGroup {
  dateIso: string;
  items: AgendaItem[];
}

@Component({
  selector: 'app-calendar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [VsDateInputComponent, FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './calendar.component.html',
})
export class CalendarComponent implements OnInit {
  private readonly cal = inject(CalendarService);
  private readonly notify = inject(NotificationService);

  protected readonly agenda = signal<AgendaItem[]>([]);
  protected readonly loading = signal(true);
  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected form = this.blank();

  protected readonly grouped = computed<DayGroup[]>(() => {
    const map = new Map<string, AgendaItem[]>();
    for (const item of this.agenda()) {
      const key = item.start_at.slice(0, 10);
      (map.get(key) ?? map.set(key, []).get(key)!).push(item);
    }
    return [...map.entries()].map(([dateIso, items]) => ({ dateIso, items }));
  });

  private range(): { start: string; end: string } {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const end = new Date(start);
    end.setDate(end.getDate() + 30);
    return { start: start.toISOString(), end: end.toISOString() };
  }

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      const { start, end } = this.range();
      this.agenda.set(await firstValueFrom(this.cal.agenda(start, end)));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected icon(item: AgendaItem): string {
    if (item.kind === 'hearing') return 'gavel';
    if (item.kind === 'deadline') return 'flag';
    if (item.kind === 'limitation') return 'timer';
    switch (item.event_type) {
      case 'court': return 'gavel';
      case 'appointment': return 'event_available';
      case 'reminder': return 'notifications';
      default: return 'event';
    }
  }

  protected async submit(): Promise<void> {
    const title = this.form.title.trim();
    if (!title || !this.form.start_at || this.saving()) return;
    this.saving.set(true);
    try {
      await firstValueFrom(
        this.cal.create({
          title,
          event_type: this.form.event_type,
          start_at: new Date(this.form.start_at).toISOString(),
          location: this.form.location.trim() || null,
        }),
      );
      this.form = this.blank();
      this.showForm.set(false);
      this.notify.success('Event added.');
      await this.load();
    } catch {
      /* handled */
    } finally {
      this.saving.set(false);
    }
  }

  protected async deleteEvent(item: AgendaItem): Promise<void> {
    if (item.kind !== 'event') return;
    try {
      await firstValueFrom(this.cal.remove(item.id));
      this.agenda.update((l) => l.filter((x) => x.id !== item.id));
    } catch {
      /* handled */
    }
  }

  private blank(): { title: string; event_type: EventType; start_at: string; location: string } {
    return { title: '', event_type: 'meeting', start_at: '', location: '' };
  }
}

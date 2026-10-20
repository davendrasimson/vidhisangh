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
import { WhatsappRemindersComponent } from '@shared/whatsapp-reminders/whatsapp-reminders.component';

interface DayGroup {
  dateIso: string;
  items: AgendaItem[];
}

type CalendarView = 'week' | 'month' | 'detailed';
interface CalendarDay extends DayGroup { date: Date; inMonth: boolean; isToday: boolean; }

@Component({
  selector: 'app-calendar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [VsDateInputComponent, FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, WhatsappRemindersComponent],
  templateUrl: './calendar.component.html',
  styleUrl: './calendar.component.scss',
})
export class CalendarComponent implements OnInit {
  private readonly cal = inject(CalendarService);
  private readonly notify = inject(NotificationService);

  protected readonly agenda = signal<AgendaItem[]>([]);
  protected readonly loading = signal(true);
  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected readonly view = signal<CalendarView>(this.initialView());
  protected readonly focusDate = signal(this.startOfDay(new Date()));
  protected form = this.blank();

  protected readonly grouped = computed<DayGroup[]>(() => {
    const map = new Map<string, AgendaItem[]>();
    for (const item of this.agenda()) {
      const key = this.localDateKey(new Date(item.start_at));
      (map.get(key) ?? map.set(key, []).get(key)!).push(item);
    }
    return [...map.entries()].map(([dateIso, items]) => ({ dateIso, items }));
  });

  protected readonly title = computed(() => {
    const focus = this.focusDate();
    if (this.view() === 'month') return this.format(focus, { month: 'long', year: 'numeric' });
    if (this.view() === 'week') {
      const start = this.startOfWeek(focus);
      const end = this.addDays(start, 6);
      return `${this.format(start, { day: 'numeric', month: 'short' })} – ${this.format(end, { day: 'numeric', month: 'short', year: 'numeric' })}`;
    }
    const end = this.addDays(focus, 29);
    return `${this.format(focus, { day: 'numeric', month: 'short' })} – ${this.format(end, { day: 'numeric', month: 'short', year: 'numeric' })}`;
  });

  protected readonly weekDays = computed<CalendarDay[]>(() => this.makeDays(this.startOfWeek(this.focusDate()), 7, this.focusDate().getMonth()));
  protected readonly monthDays = computed<CalendarDay[]>(() => {
    const focus = this.focusDate();
    const first = new Date(focus.getFullYear(), focus.getMonth(), 1);
    return this.makeDays(this.startOfWeek(first), 42, focus.getMonth());
  });

  private range(): { start: string; end: string } {
    const focus = this.focusDate();
    let start: Date;
    let end: Date;
    if (this.view() === 'week') {
      start = this.startOfWeek(focus);
      end = this.addDays(start, 7);
    } else if (this.view() === 'month') {
      start = this.startOfWeek(new Date(focus.getFullYear(), focus.getMonth(), 1));
      end = this.addDays(start, 42);
    } else {
      start = this.startOfDay(focus);
      end = this.addDays(start, 30);
    }
    return { start: start.toISOString(), end: end.toISOString() };
  }

  protected async setView(view: CalendarView): Promise<void> {
    this.view.set(view);
    localStorage.setItem('vs.calendar.view', view);
    await this.load();
  }

  protected async move(direction: -1 | 1): Promise<void> {
    const next = new Date(this.focusDate());
    if (this.view() === 'month') next.setMonth(next.getMonth() + direction, 1);
    else next.setDate(next.getDate() + direction * (this.view() === 'week' ? 7 : 30));
    this.focusDate.set(next);
    await this.load();
  }

  protected async goToday(): Promise<void> {
    this.focusDate.set(this.startOfDay(new Date()));
    await this.load();
  }

  protected async openDay(day: CalendarDay): Promise<void> {
    this.focusDate.set(this.startOfDay(day.date));
    await this.setView('detailed');
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

  protected itemTime(item: AgendaItem): string {
    return item.all_day ? 'All day' : this.format(new Date(item.start_at), { hour: 'numeric', minute: '2-digit' });
  }

  protected kindLabel(item: AgendaItem): string {
    return item.kind === 'event' ? (item.event_type?.replace('_', ' ') || 'event') : item.kind;
  }

  private makeDays(start: Date, count: number, activeMonth: number): CalendarDay[] {
    const groups = new Map(this.grouped().map((day) => [day.dateIso, day.items]));
    const today = this.localDateKey(new Date());
    return Array.from({ length: count }, (_, index) => {
      const date = this.addDays(start, index);
      const dateIso = this.localDateKey(date);
      return { date, dateIso, items: groups.get(dateIso) ?? [], inMonth: date.getMonth() === activeMonth, isToday: dateIso === today };
    });
  }

  private initialView(): CalendarView {
    const saved = localStorage.getItem('vs.calendar.view');
    return saved === 'week' || saved === 'month' || saved === 'detailed' ? saved : 'detailed';
  }

  private startOfDay(value: Date): Date { return new Date(value.getFullYear(), value.getMonth(), value.getDate()); }
  private startOfWeek(value: Date): Date { const start = this.startOfDay(value); start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); return start; }
  private addDays(value: Date, days: number): Date { const result = new Date(value); result.setDate(result.getDate() + days); return result; }
  private localDateKey(value: Date): string { return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`; }
  private format(value: Date, options: Intl.DateTimeFormatOptions): string { return new Intl.DateTimeFormat('en-IN', options).format(value); }

  private blank(): { title: string; event_type: EventType; start_at: string; location: string } {
    return { title: '', event_type: 'meeting', start_at: '', location: '' };
  }
}

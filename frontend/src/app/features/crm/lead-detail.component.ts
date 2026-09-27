import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { CrmService } from '@core/services/crm.service';
import { NotificationService } from '@core/services/notification.service';
import { ActivityType, LeadActivity, LeadDetail, LeadStatus } from '@core/models/crm.models';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';

@Component({
  selector: 'app-lead-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [VsDateInputComponent, FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './lead-detail.component.html',
})
export class LeadDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly crm = inject(CrmService);
  private readonly notify = inject(NotificationService);

  private id = '';
  protected readonly lead = signal<LeadDetail | null>(null);
  protected readonly loading = signal(true);

  protected readonly statuses: LeadStatus[] = ['new', 'contacted', 'qualified', 'consultation', 'won', 'lost'];
  protected readonly activityTypes: ActivityType[] = ['note', 'call', 'email', 'meeting', 'consultation'];
  protected activityForm = { type: 'call' as ActivityType, subject: '', due_on: '' };

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
      this.lead.set(await firstValueFrom(this.crm.get(this.id)));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected label(s: string): string {
    return s.replace('_', ' ');
  }

  private patch(changes: Partial<LeadDetail>): void {
    this.lead.update((l) => (l ? { ...l, ...changes } : l));
  }

  protected async setStatus(status: LeadStatus): Promise<void> {
    try {
      await firstValueFrom(this.crm.setStatus(this.id, status));
      this.patch({ status });
    } catch {
      /* handled */
    }
  }

  protected async addActivity(): Promise<void> {
    if (!this.activityForm.subject.trim() && this.activityForm.type === 'note') return;
    try {
      const created = await firstValueFrom(
        this.crm.addActivity(this.id, {
          type: this.activityForm.type,
          subject: this.activityForm.subject.trim() || undefined,
          due_on: this.activityForm.due_on || null,
        }),
      );
      this.patch({ activities: [...(this.lead()?.activities ?? []), created] });
      this.activityForm = { type: 'call', subject: '', due_on: '' };
    } catch {
      /* handled */
    }
  }

  protected async toggleActivity(a: LeadActivity): Promise<void> {
    try {
      const updated = await firstValueFrom(this.crm.completeActivity(a.id, !a.completed));
      this.patch({
        activities: (this.lead()?.activities ?? []).map((x) => (x.id === a.id ? updated : x)),
      });
    } catch {
      /* handled */
    }
  }

  protected async convert(): Promise<void> {
    try {
      const { matter_id } = await firstValueFrom(this.crm.convert(this.id));
      this.notify.success('Lead converted to a matter.');
      await this.router.navigate(['/app/matters', matter_id]);
    } catch {
      /* handled */
    }
  }
}

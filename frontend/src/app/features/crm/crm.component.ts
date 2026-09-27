import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { CrmService } from '@core/services/crm.service';
import { NotificationService } from '@core/services/notification.service';
import { LeadSource, PipelineColumn, SourceStat } from '@core/models/crm.models';

@Component({
  selector: 'app-crm',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './crm.component.html',
})
export class CrmComponent implements OnInit {
  private readonly crm = inject(CrmService);
  private readonly notify = inject(NotificationService);

  protected readonly pipeline = signal<PipelineColumn[]>([]);
  protected readonly sources = signal<SourceStat[]>([]);
  protected readonly loading = signal(true);

  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected form = this.blank();

  protected readonly sourceOptions: LeadSource[] = ['referral', 'website', 'walk_in', 'call', 'social', 'other'];

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.loading.set(true);
    try {
      const [pipeline, sources] = await Promise.all([
        firstValueFrom(this.crm.pipeline()),
        firstValueFrom(this.crm.sourceAnalytics()),
      ]);
      this.pipeline.set(pipeline);
      this.sources.set(sources);
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected rupees(value: string | number): string {
    const n = Number(value);
    return n ? `₹${n.toLocaleString('en-IN')}` : '';
  }

  protected label(s: string): string {
    return s.replace('_', ' ');
  }

  protected async submit(): Promise<void> {
    if (!this.form.name.trim() || this.saving()) return;
    this.saving.set(true);
    try {
      await firstValueFrom(
        this.crm.create({
          name: this.form.name.trim(),
          source: this.form.source,
          practice_area: this.form.practice_area.trim() || null,
          referred_by: this.form.referred_by.trim() || null,
          estimated_value: this.form.estimated_value ?? null,
          phone: this.form.phone.trim() || null,
          email: this.form.email.trim() || null,
        }),
      );
      this.notify.success('Lead added.');
      this.form = this.blank();
      this.showForm.set(false);
      await this.reload();
    } catch {
      /* handled */
    } finally {
      this.saving.set(false);
    }
  }

  private blank() {
    return {
      name: '', source: 'referral' as LeadSource, practice_area: '', referred_by: '',
      estimated_value: null as number | null, phone: '', email: '',
    };
  }
}

import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { FeatureFlagService } from '@core/services/feature-flag.service';
import { NotificationService } from '@core/services/notification.service';
import { FeatureFlag } from '@core/models/feature-flag.models';

@Component({
  selector: 'app-feature-flags',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatSlideToggleModule],
  templateUrl: './feature-flags.component.html',
})
export class FeatureFlagsComponent implements OnInit {
  private readonly flags = inject(FeatureFlagService);
  private readonly notify = inject(NotificationService);

  protected readonly items = signal<FeatureFlag[]>([]);
  protected readonly loading = signal(true);
  protected readonly saving = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    try {
      this.items.set(await firstValueFrom(this.flags.list()));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected async toggle(flag: FeatureFlag, enabled: boolean): Promise<void> {
    this.saving.set(flag.key);
    try {
      const updated = await firstValueFrom(this.flags.set(flag.key, enabled));
      this.items.update((list) => list.map((f) => (f.key === flag.key ? updated : f)));
      this.notify.success(`${flag.name} ${enabled ? 'enabled' : 'disabled'}.`);
    } catch {
      await this.ngOnInit();
    } finally {
      this.saving.set(null);
    }
  }
}

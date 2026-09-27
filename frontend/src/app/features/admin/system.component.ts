import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AdminService } from '@core/services/admin.service';
import { SystemOverview } from '@core/models/system.models';

@Component({
  selector: 'app-system',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [],
  templateUrl: './system.component.html',
})
export class SystemComponent implements OnInit {
  private readonly admin = inject(AdminService);

  protected readonly data = signal<SystemOverview | null>(null);
  protected readonly loading = signal(true);

  async ngOnInit(): Promise<void> {
    try {
      this.data.set(await firstValueFrom(this.admin.system()));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  /** Semantic tone for a status string, for dot/badge colouring. */
  protected tone(status: string): 'ok' | 'warn' | 'bad' {
    if (['ok', 'live'].includes(status)) return 'ok';
    if (['error', 'unreachable'].includes(status)) return 'bad';
    return 'warn'; // log-fallback, mock, not_configured, storage backend, etc.
  }

  protected label(s: string): string {
    return s.replace(/[_-]/g, ' ');
  }
}

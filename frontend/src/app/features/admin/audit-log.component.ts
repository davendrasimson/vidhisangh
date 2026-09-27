import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { AdminService } from '@core/services/admin.service';
import { AuditEvent } from '@core/models/audit.models';

@Component({
  selector: 'app-audit-log',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatIconModule],
  templateUrl: './audit-log.component.html',
})
export class AuditLogComponent implements OnInit {
  private readonly admin = inject(AdminService);

  protected readonly events = signal<AuditEvent[]>([]);
  protected readonly loading = signal(true);

  async ngOnInit(): Promise<void> {
    try {
      this.events.set(await firstValueFrom(this.admin.audit()));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected icon(action: string): string {
    if (action.startsWith('feature_flag')) return 'toggle_on';
    if (action.startsWith('subscription')) return 'workspace_premium';
    if (action.startsWith('user') || action.startsWith('role')) return 'manage_accounts';
    return 'history';
  }
}

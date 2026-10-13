import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { PortalService } from '@core/services/portal.service';
import { PortalApproval, PortalDocument, PortalView } from '@core/models/portal.models';

import { saveBlob } from '@core/platform/save-file';
@Component({
  selector: 'app-client-portal',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatIconModule, MatButtonModule],
  templateUrl: './client-portal.component.html',
})
export class ClientPortalComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly portal = inject(PortalService);

  private readonly token = this.route.snapshot.paramMap.get('token') ?? '';
  protected readonly view = signal<PortalView | null>(null);
  protected readonly loading = signal(true);
  protected readonly invalid = signal(false);

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.view.set(await firstValueFrom(this.portal.view(this.token)));
    } catch {
      this.invalid.set(true);
    } finally {
      this.loading.set(false);
    }
  }

  private patchApproval(updated: PortalApproval): void {
    this.view.update((v) =>
      v ? { ...v, approvals: v.approvals.map((a) => (a.id === updated.id ? updated : a)) } : v,
    );
  }

  protected async respond(a: PortalApproval, approve: boolean): Promise<void> {
    try {
      this.patchApproval(await firstValueFrom(this.portal.respond(this.token, a.id, approve)));
    } catch {
      /* handled */
    }
  }

  protected async download(doc: PortalDocument): Promise<void> {
    try {
      const blob = await firstValueFrom(this.portal.clientDownload(this.token, doc.id));
      await saveBlob(blob, doc.name);
    } catch {
      /* handled */
    }
  }
}

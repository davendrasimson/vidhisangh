import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { PortalService } from '@core/services/portal.service';
import { DocumentsService } from '@core/services/documents.service';
import { NotificationService } from '@core/services/notification.service';
import { PortalAccess, PortalApproval } from '@core/models/portal.models';
import { DocFile } from '@core/models/documents.models';

import { publicOrigin } from '@core/platform/platform';
@Component({
  selector: 'app-matter-portal',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, MatButtonModule, MatTooltipModule],
  templateUrl: './matter-portal.component.html',
})
export class MatterPortalComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly portal = inject(PortalService);
  private readonly docs = inject(DocumentsService);
  private readonly notify = inject(NotificationService);

  protected readonly matterId = this.route.snapshot.paramMap.get('id') ?? '';
  protected readonly accesses = signal<PortalAccess[]>([]);
  protected readonly approvals = signal<PortalApproval[]>([]);
  protected readonly documents = signal<DocFile[]>([]);
  protected readonly sharedIds = signal<Set<string>>(new Set());
  protected readonly loading = signal(true);

  protected grantForm = { client_name: '', client_email: '' };
  protected updateForm = { title: '', body: '' };
  protected approvalForm = { title: '', description: '' };

  constructor() {
    void this.loadAll();
  }

  private async loadAll(): Promise<void> {
    this.loading.set(true);
    try {
      const [accesses, approvals, documents, shared] = await Promise.all([
        firstValueFrom(this.portal.listAccess(this.matterId)),
        firstValueFrom(this.portal.approvals(this.matterId)),
        firstValueFrom(this.docs.list({ matterId: this.matterId })),
        firstValueFrom(this.portal.sharedDocumentIds(this.matterId)),
      ]);
      this.accesses.set(accesses);
      this.approvals.set(approvals);
      this.documents.set(documents);
      this.sharedIds.set(new Set(shared));
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected link(a: PortalAccess): string {
    return `${publicOrigin()}/portal/${a.token}`;
  }

  protected async copyLink(a: PortalAccess): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.link(a));
      this.notify.success('Portal link copied.');
    } catch {
      this.notify.info(this.link(a));
    }
  }

  protected async grant(): Promise<void> {
    const { client_name, client_email } = this.grantForm;
    if (!client_name.trim() || !client_email.trim()) return;
    try {
      const created = await firstValueFrom(
        this.portal.grantAccess(this.matterId, client_name.trim(), client_email.trim()),
      );
      this.accesses.update((l) => [created, ...l]);
      this.grantForm = { client_name: '', client_email: '' };
      this.notify.success('Portal access granted.');
    } catch {
      /* handled */
    }
  }

  protected async revoke(a: PortalAccess): Promise<void> {
    try {
      const updated = await firstValueFrom(this.portal.revoke(a.id));
      this.accesses.update((l) => l.map((x) => (x.id === a.id ? updated : x)));
    } catch {
      /* handled */
    }
  }

  protected async postUpdate(): Promise<void> {
    const { title, body } = this.updateForm;
    if (!title.trim() || !body.trim()) return;
    try {
      await firstValueFrom(this.portal.postUpdate(this.matterId, title.trim(), body.trim()));
      this.updateForm = { title: '', body: '' };
      this.notify.success('Update posted to the client portal.');
    } catch {
      /* handled */
    }
  }

  protected async requestApproval(): Promise<void> {
    const { title, description } = this.approvalForm;
    if (!title.trim()) return;
    try {
      const created = await firstValueFrom(
        this.portal.requestApproval(this.matterId, title.trim(), description.trim() || undefined),
      );
      this.approvals.update((l) => [created, ...l]);
      this.approvalForm = { title: '', description: '' };
    } catch {
      /* handled */
    }
  }

  protected isShared(doc: DocFile): boolean {
    return this.sharedIds().has(doc.id);
  }

  protected async toggleShare(doc: DocFile): Promise<void> {
    const shared = this.isShared(doc);
    try {
      if (shared) await firstValueFrom(this.portal.unshareDocument(this.matterId, doc.id));
      else await firstValueFrom(this.portal.shareDocument(this.matterId, doc.id));
      this.sharedIds.update((s) => {
        const next = new Set(s);
        if (shared) next.delete(doc.id);
        else next.add(doc.id);
        return next;
      });
    } catch {
      /* handled */
    }
  }
}

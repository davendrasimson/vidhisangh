import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { GroupsService } from '@core/services/groups.service';
import { NotificationService } from '@core/services/notification.service';
import { Group, GroupType, GroupVisibility, Invitation } from '@core/models/groups.models';

type Tab = 'discover' | 'mine';

@Component({
  selector: 'app-groups',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './groups.component.html',
})
export class GroupsComponent implements OnInit {
  private readonly groups = inject(GroupsService);
  private readonly notify = inject(NotificationService);

  protected readonly tab = signal<Tab>('discover');
  protected readonly discoverList = signal<Group[]>([]);
  protected readonly mineList = signal<Group[]>([]);
  protected readonly invitations = signal<Invitation[]>([]);
  protected readonly loading = signal(true);

  // Create-group form.
  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected form = this.blankForm();

  async ngOnInit(): Promise<void> {
    await Promise.all([this.reload(), this.loadInvitations()]);
  }

  private async loadInvitations(): Promise<void> {
    try {
      this.invitations.set(await firstValueFrom(this.groups.invitations()));
    } catch {
      /* handled */
    }
  }

  protected async acceptInvite(inv: Invitation): Promise<void> {
    try {
      const group = await firstValueFrom(this.groups.acceptInvite(inv.group_id));
      this.invitations.update((list) => list.filter((i) => i.group_id !== inv.group_id));
      this.mineList.update((list) => [group, ...list.filter((g) => g.id !== group.id)]);
      this.notify.success(`You joined ${inv.group_name}.`);
    } catch {
      /* handled */
    }
  }

  protected async declineInvite(inv: Invitation): Promise<void> {
    try {
      await firstValueFrom(this.groups.declineInvite(inv.group_id));
      this.invitations.update((list) => list.filter((i) => i.group_id !== inv.group_id));
    } catch {
      /* handled */
    }
  }

  protected async switchTab(tab: Tab): Promise<void> {
    if (this.tab() === tab) return;
    this.tab.set(tab);
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.loading.set(true);
    try {
      if (this.tab() === 'discover') {
        this.discoverList.set(await firstValueFrom(this.groups.discover()));
      } else {
        this.mineList.set(await firstValueFrom(this.groups.myGroups()));
      }
    } catch {
      /* handled by interceptor */
    } finally {
      this.loading.set(false);
    }
  }

  protected list(): Group[] {
    return this.tab() === 'discover' ? this.discoverList() : this.mineList();
  }

  protected initials(name: string): string {
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || '?';
  }

  protected async join(group: Group, event: Event): Promise<void> {
    event.stopPropagation();
    event.preventDefault();
    try {
      const membership = await firstValueFrom(this.groups.join(group.id));
      this.patchDiscover(group.id, {
        my_status: membership.status,
        my_role: membership.role,
        member_count: group.member_count + (membership.status === 'active' ? 1 : 0),
      });
      this.notify.success(
        membership.status === 'active'
          ? `You joined ${group.name}.`
          : `Request to join ${group.name} sent for approval.`,
      );
    } catch {
      /* handled */
    }
  }

  protected async submit(): Promise<void> {
    const name = this.form.name.trim();
    if (name.length < 2 || this.saving()) return;
    this.saving.set(true);
    try {
      const created = await firstValueFrom(
        this.groups.create({
          name,
          description: this.form.description.trim() || null,
          group_type: this.form.group_type,
          visibility: this.form.visibility,
        }),
      );
      this.notify.success(`${created.name} created.`);
      this.form = this.blankForm();
      this.showForm.set(false);
      this.mineList.update((list) => [created, ...list]);
      if (this.tab() === 'discover') this.discoverList.update((list) => [created, ...list]);
    } catch {
      /* handled */
    } finally {
      this.saving.set(false);
    }
  }

  private patchDiscover(id: string, changes: Partial<Group>): void {
    this.discoverList.update((list) =>
      list.map((g) => (g.id === id ? { ...g, ...changes } : g)),
    );
  }

  private blankForm(): {
    name: string;
    description: string;
    group_type: GroupType;
    visibility: GroupVisibility;
  } {
    return { name: '', description: '', group_type: 'community', visibility: 'public' };
  }
}

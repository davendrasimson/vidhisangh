import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { NetworkService } from '@core/services/network.service';
import { NotificationService } from '@core/services/notification.service';
import { Connection, DirectoryPerson } from '@core/models/network.models';

@Component({
  selector: 'app-people',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './people.component.html',
})
export class PeopleComponent implements OnInit {
  private readonly net = inject(NetworkService);
  private readonly notify = inject(NotificationService);

  protected readonly people = signal<DirectoryPerson[]>([]);
  protected readonly requests = signal<Connection[]>([]);
  protected readonly loading = signal(true);

  private readonly nameById = computed(() => {
    const map: Record<string, string> = {};
    for (const p of this.people()) map[p.user_id] = p.display_name;
    return map;
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.loading.set(true);
    try {
      const [people, requests] = await Promise.all([
        firstValueFrom(this.net.directory()),
        firstValueFrom(this.net.incomingRequests()),
      ]);
      this.people.set(people);
      this.requests.set(requests);
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  protected requesterName(c: Connection): string {
    return this.nameById()[c.requester_id] ?? 'A professional';
  }

  protected initials(name: string): string {
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || '?';
  }

  protected async connect(person: DirectoryPerson): Promise<void> {
    try {
      await firstValueFrom(this.net.connect(person.user_id));
      this.patch(person.user_id, { connection_status: 'pending_out' });
      this.notify.success(`Connection request sent to ${person.display_name}.`);
    } catch {
      /* handled */
    }
  }

  protected async toggleFollow(person: DirectoryPerson): Promise<void> {
    const following = person.is_following;
    this.patch(person.user_id, { is_following: !following });
    try {
      await firstValueFrom(following ? this.net.unfollow(person.user_id) : this.net.follow(person.user_id));
    } catch {
      this.patch(person.user_id, { is_following: following });
    }
  }

  protected async accept(c: Connection): Promise<void> {
    try {
      await firstValueFrom(this.net.acceptConnection(c.id));
      this.notify.success('Connection accepted.');
      await this.reload();
    } catch {
      /* handled */
    }
  }

  protected async decline(c: Connection): Promise<void> {
    try {
      await firstValueFrom(this.net.declineConnection(c.id));
      await this.reload();
    } catch {
      /* handled */
    }
  }

  private patch(userId: string, changes: Partial<DirectoryPerson>): void {
    this.people.update((list) =>
      list.map((p) => (p.user_id === userId ? { ...p, ...changes } : p)),
    );
  }
}

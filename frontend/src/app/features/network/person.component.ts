import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { NetworkService } from '@core/services/network.service';
import { MessagingService } from '@core/services/messaging.service';
import { NotificationService } from '@core/services/notification.service';
import { FeedItem, PublicProfile } from '@core/models/network.models';

@Component({
  selector: 'app-person',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './person.component.html',
})
export class PersonComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly net = inject(NetworkService);
  private readonly messaging = inject(MessagingService);
  private readonly notify = inject(NotificationService);

  protected readonly person = signal<PublicProfile | null>(null);
  protected readonly posts = signal<FeedItem[]>([]);
  protected readonly loading = signal(true);

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      const id = params.get('id');
      if (id) void this.load(id);
    });
  }

  private async load(id: string): Promise<void> {
    this.loading.set(true);
    this.person.set(null);
    this.posts.set([]);
    try {
      const [person, posts] = await Promise.all([
        firstValueFrom(this.net.person(id)),
        firstValueFrom(this.net.userPosts(id)),
      ]);
      this.person.set(person);
      this.posts.set(posts);
    } catch {
      /* handled by interceptor */
    } finally {
      this.loading.set(false);
    }
  }

  protected initials(name: string): string {
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || '?';
  }

  private patch(changes: Partial<PublicProfile>): void {
    this.person.update((p) => (p ? { ...p, ...changes } : p));
  }

  protected async connect(): Promise<void> {
    const p = this.person();
    if (!p) return;
    try {
      await firstValueFrom(this.net.connect(p.user_id));
      this.patch({ connection_status: 'pending_out' });
      this.notify.success(`Connection request sent to ${p.display_name}.`);
    } catch {
      /* handled */
    }
  }

  protected async toggleFollow(): Promise<void> {
    const p = this.person();
    if (!p) return;
    const following = p.is_following;
    this.patch({ is_following: !following });
    try {
      await firstValueFrom(following ? this.net.unfollow(p.user_id) : this.net.follow(p.user_id));
    } catch {
      this.patch({ is_following: following });
    }
  }

  protected async message(): Promise<void> {
    const p = this.person();
    if (!p) return;
    try {
      await firstValueFrom(this.messaging.startDirect(p.user_id));
      await this.router.navigate(['/app/messages']);
    } catch {
      /* handled */
    }
  }
}

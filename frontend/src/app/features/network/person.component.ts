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
import { ProfileService } from '@core/services/profile.service';
import { FeedItem, PublicProfile } from '@core/models/network.models';
import { ProfileDetail } from '@core/models/profile.models';

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
  protected imageUrl(id: string): string { return this.net.postImageUrl(id); }
  private readonly messaging = inject(MessagingService);
  private readonly notify = inject(NotificationService);
  private readonly profiles = inject(ProfileService);

  protected readonly person = signal<PublicProfile | null>(null);
  protected readonly professionalProfile = signal<ProfileDetail | null>(null);
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
    this.professionalProfile.set(null);
    this.posts.set([]);
    try {
      const [personResult, postsResult, profileResult] = await Promise.allSettled([
        firstValueFrom(this.net.person(id)),
        firstValueFrom(this.net.userPosts(id)),
        firstValueFrom(this.profiles.getProfile(id)),
      ]);
      if (personResult.status === 'fulfilled') this.person.set(personResult.value);
      if (postsResult.status === 'fulfilled') this.posts.set(postsResult.value);
      if (profileResult.status === 'fulfilled') this.professionalProfile.set(profileResult.value);
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

  protected async block(): Promise<void> {
    const p = this.person();
    if (!p || !confirm(`Block ${p.display_name}? Their posts, comments and messages disappear for you, and they cannot connect with or message you. You can unblock later under Settings → Privacy.`)) return;
    try {
      await firstValueFrom(this.net.block(p.user_id));
      this.person.set({ ...p, is_blocked: true, connection_status: null, is_following: false });
      this.notify.success(`${p.display_name} is blocked.`);
    } catch {
      this.notify.error('Could not block this member. Please try again.');
    }
  }

  protected async unblock(): Promise<void> {
    const p = this.person();
    if (!p) return;
    try {
      await firstValueFrom(this.net.unblock(p.user_id));
      this.person.set({ ...p, is_blocked: false });
      this.notify.success(`${p.display_name} is unblocked.`);
    } catch {
      this.notify.error('Could not unblock this member. Please try again.');
    }
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

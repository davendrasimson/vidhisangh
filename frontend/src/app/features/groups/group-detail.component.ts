import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { HttpClient } from '@angular/common/http';
import { environment } from '@env/environment';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { AuthService } from '@core/auth/auth.service';
import { GroupsService } from '@core/services/groups.service';
import { NetworkService } from '@core/services/network.service';
import { NotificationService } from '@core/services/notification.service';
import { Group, GroupComment, GroupMember, GroupPost } from '@core/models/groups.models';
import { DirectoryPerson } from '@core/models/network.models';

type Section = 'feed' | 'members';

@Component({
  selector: 'app-group-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, MatMenuModule],
  templateUrl: './group-detail.component.html',
})
export class GroupDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly groups = inject(GroupsService);
  private readonly net = inject(NetworkService);
  private readonly notify = inject(NotificationService);
  private readonly auth = inject(AuthService);
  private readonly http = inject(HttpClient);

  private groupId = '';
  protected readonly group = signal<Group | null>(null);
  protected readonly members = signal<GroupMember[]>([]);
  protected readonly requests = signal<GroupMember[]>([]);
  protected readonly posts = signal<GroupPost[]>([]);
  protected readonly loading = signal(true);
  protected readonly section = signal<Section>('feed');
  protected readonly draft = signal('');
  protected readonly posting = signal(false);

  // Per-post comment UI state.
  protected readonly openComments = signal<Record<string, GroupComment[] | undefined>>({});
  protected readonly commentDraft = signal<Record<string, string>>({});

  // Invite-from-directory panel (managers).
  protected readonly showInvite = signal(false);
  protected readonly directory = signal<DirectoryPerson[]>([]);
  protected readonly invitedIds = signal<Set<string>>(new Set());
  protected readonly invitable = computed(() => {
    const members = new Set(this.members().map((m) => m.user_id));
    return this.directory().filter((p) => !members.has(p.user_id));
  });

  protected readonly isMember = computed(() => this.group()?.my_status === 'active');
  protected readonly isManager = computed(() => {
    const role = this.group()?.my_role;
    return role === 'owner' || role === 'admin';
  });
  protected readonly isOwner = computed(() => this.group()?.my_role === 'owner');
  protected readonly inviteLink = signal<{ code: string; url: string } | null>(null);
  protected readonly inviteWhatsApp = computed(() => {
    const g = this.group(), link = this.inviteLink();
    return g && link ? `https://wa.me/?text=${encodeURIComponent(`Join ${g.name} on VidhiSangh: ${link.url}`)}` : '';
  });

  protected async loadInviteLink(reset: boolean): Promise<void> {
    const g = this.group();
    if (!g || (reset && !window.confirm('Make a new link? The old one will stop working.'))) return;
    try {
      this.inviteLink.set(await firstValueFrom(this.http.post<{ code: string; url: string }>(
        `${environment.apiBaseUrl}/groups/${g.id}/invite-link${reset ? '?reset=true' : ''}`, {})));
      if (reset) this.notify.success('New invite link ready; the old one no longer works.');
    } catch { /* toast shown */ }
  }

  protected async copyInviteLink(url: string): Promise<void> {
    try { await navigator.clipboard.writeText(url); this.notify.success('Invite link copied.'); } catch { /* clipboard unavailable */ }
  }
  protected readonly myId = computed(() => this.auth.user()?.id ?? '');
  protected readonly myInitials = computed(() => this.initials(this.auth.user()?.full_name ?? ''));

  async ngOnInit(): Promise<void> {
    this.groupId = this.route.snapshot.paramMap.get('id') ?? '';
    await this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      const group = await firstValueFrom(this.groups.get(this.groupId));
      this.group.set(group);
      await this.refreshMemberViews();
      if (group.my_status === 'active') {
        this.posts.set(await firstValueFrom(this.groups.posts(this.groupId)));
      }
    } catch {
      /* handled */
    } finally {
      this.loading.set(false);
    }
  }

  private async refreshMemberViews(): Promise<void> {
    if (!this.isMember()) return;
    this.members.set(await firstValueFrom(this.groups.members(this.groupId)));
    if (this.isManager()) {
      this.requests.set(await firstValueFrom(this.groups.requests(this.groupId)));
    }
  }

  protected initials(name: string): string {
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || '?';
  }

  // ── Membership ─────────────────────────────────────────────────
  protected async join(): Promise<void> {
    const group = this.group();
    if (!group) return;
    try {
      const m = await firstValueFrom(this.groups.join(group.id));
      this.notify.success(
        m.status === 'active' ? `You joined ${group.name}.` : 'Request sent for approval.',
      );
      await this.load();
    } catch {
      /* handled */
    }
  }

  protected async leave(): Promise<void> {
    const group = this.group();
    if (!group) return;
    try {
      await firstValueFrom(this.groups.leave(group.id));
      this.notify.info(`You left ${group.name}.`);
      await this.load();
    } catch {
      /* handled */
    }
  }

  protected async deleteGroup(): Promise<void> {
    const group = this.group();
    if (!group) return;
    try {
      await firstValueFrom(this.groups.remove(group.id));
      this.notify.success(`${group.name} deleted.`);
      await this.router.navigate(['/app/groups']);
    } catch {
      /* handled */
    }
  }

  // ── Moderation ─────────────────────────────────────────────────
  protected async approve(m: GroupMember): Promise<void> {
    try {
      await firstValueFrom(this.groups.approve(this.groupId, m.user_id));
      this.notify.success(`${m.member_name} approved.`);
      await this.load();
    } catch {
      /* handled */
    }
  }

  protected async reject(m: GroupMember): Promise<void> {
    try {
      await firstValueFrom(this.groups.reject(this.groupId, m.user_id));
      this.requests.update((list) => list.filter((r) => r.user_id !== m.user_id));
    } catch {
      /* handled */
    }
  }

  protected async promote(m: GroupMember): Promise<void> {
    await this.changeRole(m, m.role === 'admin' ? 'member' : 'admin');
  }

  private async changeRole(m: GroupMember, role: 'admin' | 'member'): Promise<void> {
    try {
      const updated = await firstValueFrom(this.groups.setRole(this.groupId, m.user_id, role));
      this.members.update((list) => list.map((x) => (x.user_id === m.user_id ? updated : x)));
      this.notify.success(`${m.member_name} is now ${role}.`);
    } catch {
      /* handled */
    }
  }

  protected async removeMember(m: GroupMember): Promise<void> {
    try {
      await firstValueFrom(this.groups.removeMember(this.groupId, m.user_id));
      this.members.update((list) => list.filter((x) => x.user_id !== m.user_id));
      this.patchGroup({ member_count: Math.max(0, (this.group()?.member_count ?? 1) - 1) });
    } catch {
      /* handled */
    }
  }

  // ── Inviting people ────────────────────────────────────────────
  protected async toggleInvitePanel(): Promise<void> {
    const next = !this.showInvite();
    this.showInvite.set(next);
    if (next && this.directory().length === 0) {
      try {
        this.directory.set(await firstValueFrom(this.net.directory()));
      } catch {
        /* handled */
      }
    }
  }

  protected async invitePerson(person: DirectoryPerson): Promise<void> {
    try {
      await firstValueFrom(this.groups.invite(this.groupId, person.user_id));
      this.invitedIds.update((set) => new Set(set).add(person.user_id));
      this.notify.success(`Invitation sent to ${person.display_name}.`);
    } catch {
      /* handled */
    }
  }

  protected isInvited(userId: string): boolean {
    return this.invitedIds().has(userId);
  }

  // ── Community feed ─────────────────────────────────────────────
  protected async publish(): Promise<void> {
    const content = this.draft().trim();
    if (!content || this.posting()) return;
    this.posting.set(true);
    try {
      const post = await firstValueFrom(this.groups.createPost(this.groupId, content));
      this.posts.update((list) => [post, ...list]);
      this.patchGroup({ post_count: (this.group()?.post_count ?? 0) + 1 });
      this.draft.set('');
    } catch {
      /* handled */
    } finally {
      this.posting.set(false);
    }
  }

  protected async toggleLike(post: GroupPost): Promise<void> {
    const liked = post.liked;
    this.patchPost(post.id, { liked: !liked, like_count: post.like_count + (liked ? -1 : 1) });
    try {
      await firstValueFrom(liked ? this.groups.unlikePost(post.id) : this.groups.likePost(post.id));
    } catch {
      this.patchPost(post.id, { liked, like_count: post.like_count });
    }
  }

  protected async deletePost(post: GroupPost): Promise<void> {
    try {
      await firstValueFrom(this.groups.deletePost(post.id));
      this.posts.update((list) => list.filter((p) => p.id !== post.id));
      this.patchGroup({ post_count: Math.max(0, (this.group()?.post_count ?? 1) - 1) });
    } catch {
      /* handled */
    }
  }

  protected canDelete(authorId: string): boolean {
    return authorId === this.myId() || this.isManager();
  }

  // ── Comments ───────────────────────────────────────────────────
  protected async toggleComments(post: GroupPost): Promise<void> {
    const open = this.openComments();
    if (open[post.id] !== undefined) {
      this.openComments.set({ ...open, [post.id]: undefined });
      return;
    }
    try {
      const comments = await firstValueFrom(this.groups.comments(post.id));
      this.openComments.set({ ...this.openComments(), [post.id]: comments });
    } catch {
      /* handled */
    }
  }

  protected setCommentDraft(postId: string, value: string): void {
    this.commentDraft.set({ ...this.commentDraft(), [postId]: value });
  }

  protected async submitComment(post: GroupPost): Promise<void> {
    const body = (this.commentDraft()[post.id] ?? '').trim();
    if (!body) return;
    try {
      const comment = await firstValueFrom(this.groups.addComment(post.id, body));
      const current = this.openComments()[post.id] ?? [];
      this.openComments.set({ ...this.openComments(), [post.id]: [...current, comment] });
      this.setCommentDraft(post.id, '');
      this.patchPost(post.id, { comment_count: post.comment_count + 1 });
    } catch {
      /* handled */
    }
  }

  protected async deleteComment(post: GroupPost, comment: GroupComment): Promise<void> {
    try {
      await firstValueFrom(this.groups.deleteComment(comment.id));
      const current = this.openComments()[post.id] ?? [];
      this.openComments.set({
        ...this.openComments(),
        [post.id]: current.filter((c) => c.id !== comment.id),
      });
      this.patchPost(post.id, { comment_count: Math.max(0, post.comment_count - 1) });
    } catch {
      /* handled */
    }
  }

  private patchGroup(changes: Partial<Group>): void {
    this.group.update((g) => (g ? { ...g, ...changes } : g));
  }

  private patchPost(id: string, changes: Partial<GroupPost>): void {
    this.posts.update((list) => list.map((p) => (p.id === id ? { ...p, ...changes } : p)));
  }
}

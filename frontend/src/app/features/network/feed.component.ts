import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '@core/auth/auth.service';
import { NetworkService } from '@core/services/network.service';
import { NotificationService } from '@core/services/notification.service';
import {
  Comment,
  DirectoryPerson,
  FeedItem,
  LinkPreview,
  TrendingTag,
} from '@core/models/network.models';

@Component({
  selector: 'app-feed',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule],
  templateUrl: './feed.component.html',
  styleUrl: './feed.component.scss',
})
export class FeedComponent implements OnInit {
  private readonly net = inject(NetworkService);
  private readonly notify = inject(NotificationService);
  protected readonly auth = inject(AuthService);

  protected readonly posts = signal<FeedItem[]>([]);
  protected readonly loading = signal(true);
  protected readonly draft = signal('');
  protected readonly posting = signal(false);
  protected readonly view = signal<'all' | 'saved' | 'mentions'>('all');
  protected readonly trending = signal<TrendingTag[]>([]);

  // Link preview (LinkedIn/Facebook-style unfurl) for a URL in the draft.
  protected readonly linkPreview = signal<LinkPreview | null>(null);
  protected readonly previewLoading = signal(false);
  private previewTimer?: ReturnType<typeof setTimeout>;
  private lastPreviewUrl: string | null = null;
  private readonly dismissedUrls = new Set<string>();

  // Compose-time "tag people" picker.
  protected readonly showTagPicker = signal(false);
  protected readonly directory = signal<DirectoryPerson[]>([]);
  protected readonly taggedIds = signal<Set<string>>(new Set());
  protected readonly taggedPeople = computed(() =>
    this.directory().filter((p) => this.taggedIds().has(p.user_id)),
  );

  // Per-post UI state.
  protected readonly openComments = signal<Record<string, Comment[] | undefined>>({});
  protected readonly commentDraft = signal<Record<string, string>>({});

  protected readonly myInitials = computed(() => {
    const n = this.auth.user()?.full_name ?? '';
    return n.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || 'U';
  });

  async ngOnInit(): Promise<void> {
    await Promise.all([this.load(), this.loadTrending()]);
  }

  private async loadTrending(): Promise<void> {
    try {
      this.trending.set(await firstValueFrom(this.net.trending()));
    } catch {
      /* handled */
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      const source =
        this.view() === 'saved'
          ? this.net.bookmarks()
          : this.view() === 'mentions'
            ? this.net.mentions()
            : this.net.feed();
      this.posts.set(await firstValueFrom(source));
    } catch {
      /* handled by interceptor */
    } finally {
      this.loading.set(false);
    }
  }

  protected async switchView(view: 'all' | 'saved' | 'mentions'): Promise<void> {
    if (this.view() === view) return;
    this.view.set(view);
    await this.load();
  }

  // ── Tag people ─────────────────────────────────────────────────
  protected async toggleTagPicker(): Promise<void> {
    const next = !this.showTagPicker();
    this.showTagPicker.set(next);
    if (next && this.directory().length === 0) {
      try {
        this.directory.set(await firstValueFrom(this.net.directory()));
      } catch {
        /* handled */
      }
    }
  }

  protected toggleTag(person: DirectoryPerson): void {
    this.taggedIds.update((set) => {
      const next = new Set(set);
      if (next.has(person.user_id)) next.delete(person.user_id);
      else next.add(person.user_id);
      return next;
    });
  }

  protected isTagged(userId: string): boolean {
    return this.taggedIds().has(userId);
  }

  protected async toggleBookmark(post: FeedItem): Promise<void> {
    const saved = post.bookmarked;
    this.patch(post.id, { bookmarked: !saved });
    try {
      await firstValueFrom(saved ? this.net.unbookmark(post.id) : this.net.bookmark(post.id));
      // In the Saved view, un-saving removes the card.
      if (saved && this.view() === 'saved') {
        this.posts.update((list) => list.filter((p) => p.id !== post.id));
      }
    } catch {
      this.patch(post.id, { bookmarked: saved });
    }
  }

  protected initials(name: string): string {
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || '?';
  }

  /** Draft input handler: updates the draft and debounces a link-preview fetch. */
  protected onDraftInput(value: string): void {
    this.draft.set(value);
    clearTimeout(this.previewTimer);
    const url = this.firstUrl(value);
    if (!url) {
      // No URL left in the text → drop any preview.
      this.linkPreview.set(null);
      this.previewLoading.set(false);
      this.lastPreviewUrl = null;
      return;
    }
    if (url === this.lastPreviewUrl || this.dismissedUrls.has(url)) return;
    this.previewTimer = setTimeout(() => void this.fetchPreview(url), 600);
  }

  private firstUrl(text: string): string | null {
    const m = text.match(/https?:\/\/[^\s<>"']+/i);
    return m ? m[0].replace(/[),.]+$/, '') : null;
  }

  private async fetchPreview(url: string): Promise<void> {
    this.lastPreviewUrl = url;
    this.previewLoading.set(true);
    this.linkPreview.set(null);
    try {
      const preview = await firstValueFrom(this.net.linkPreview(url));
      // Only apply if the URL is still present in the draft.
      if (this.draft().includes(url)) this.linkPreview.set(preview);
    } catch {
      this.linkPreview.set(null); // 404 / blocked / not reachable → no card
    } finally {
      this.previewLoading.set(false);
    }
  }

  /** Hide a preview image that fails to load (missing/slow OG image). */
  protected onPreviewImgError(ev: Event): void {
    (ev.target as HTMLElement).style.display = 'none';
  }

  /** Dismiss the preview and remember the URL so it isn't re-fetched. */
  protected removePreview(): void {
    const preview = this.linkPreview();
    if (preview) this.dismissedUrls.add(preview.url);
    this.linkPreview.set(null);
    this.previewLoading.set(false);
  }

  protected async publish(): Promise<void> {
    const content = this.draft().trim();
    if (!content || this.posting()) return;
    this.posting.set(true);
    try {
      const hashtags = [...content.matchAll(/#(\w+)/g)].map((m) => m[1]);
      const mention_ids = [...this.taggedIds()];
      const preview = this.linkPreview();
      const created = await firstValueFrom(
        this.net.createPost({
          content,
          hashtags,
          mention_ids,
          link_url: preview?.url ?? null,
          link_title: preview?.title ?? null,
          link_description: preview?.description ?? null,
          link_image: preview?.image ?? null,
          link_site_name: preview?.site_name ?? null,
        }),
      );
      this.posts.update((list) => [created, ...list]);
      this.draft.set('');
      this.taggedIds.set(new Set());
      this.showTagPicker.set(false);
      this.linkPreview.set(null);
      this.lastPreviewUrl = null;
      this.dismissedUrls.clear();
    } catch {
      /* handled */
    } finally {
      this.posting.set(false);
    }
  }

  protected async toggleLike(post: FeedItem): Promise<void> {
    const liked = post.my_reaction != null;
    // Optimistic update.
    this.patch(post.id, {
      my_reaction: liked ? null : 'like',
      like_count: post.like_count + (liked ? -1 : 1),
    });
    try {
      await firstValueFrom(liked ? this.net.unreact(post.id) : this.net.react(post.id, 'like'));
    } catch {
      this.patch(post.id, { my_reaction: post.my_reaction, like_count: post.like_count });
    }
  }

  protected async share(post: FeedItem): Promise<void> {
    try {
      const repost = await firstValueFrom(this.net.share(post.id));
      // Reflect the incremented share count on the source card.
      const sourceId = post.shared_from_id ?? post.id;
      this.patch(sourceId, { share_count: (this.postById(sourceId)?.share_count ?? 0) + 1 });
      if (this.view() === 'all') this.posts.update((list) => [repost, ...list]);
      this.notify.success('Reposted to your feed.');
    } catch {
      /* handled */
    }
  }

  private postById(id: string): FeedItem | undefined {
    return this.posts().find((p) => p.id === id);
  }

  protected async toggleComments(post: FeedItem): Promise<void> {
    const open = this.openComments();
    if (open[post.id] !== undefined) {
      this.openComments.set({ ...open, [post.id]: undefined });
      return;
    }
    try {
      const comments = await firstValueFrom(this.net.comments(post.id));
      this.openComments.set({ ...this.openComments(), [post.id]: comments });
    } catch {
      /* handled */
    }
  }

  protected setCommentDraft(postId: string, value: string): void {
    this.commentDraft.set({ ...this.commentDraft(), [postId]: value });
  }

  protected async submitComment(post: FeedItem): Promise<void> {
    const body = (this.commentDraft()[post.id] ?? '').trim();
    if (!body) return;
    try {
      const comment = await firstValueFrom(this.net.addComment(post.id, body));
      const current = this.openComments()[post.id] ?? [];
      this.openComments.set({ ...this.openComments(), [post.id]: [...current, comment] });
      this.setCommentDraft(post.id, '');
      this.patch(post.id, { comment_count: post.comment_count + 1 });
    } catch {
      /* handled */
    }
  }

  private patch(postId: string, changes: Partial<FeedItem>): void {
    this.posts.update((list) =>
      list.map((p) => (p.id === postId ? { ...p, ...changes } : p)),
    );
  }
}

import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '@core/auth/auth.service';
import { NetworkService } from '@core/services/network.service';
import { NotificationService } from '@core/services/notification.service';
import { ComposerValue, PostComposerComponent } from './post-composer.component';
import {
  Comment,
  DirectoryPerson,
  FeedItem,
  LinkPreview,
  PostReportCategory,
  ReactionType,
  TrendingTag,
} from '@core/models/network.models';

@Component({
  selector: 'app-feed',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, PostComposerComponent],
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
  /** What the rich composer holds: HTML, its plain text and uploaded photo ids. */
  protected readonly composed = signal<ComposerValue>({ html: '', text: '', imageIds: [], uploading: false });
  private readonly composer = viewChild(PostComposerComponent);
  protected readonly canPost = computed(() => {
    const c = this.composed();
    return !this.posting() && !c.uploading && (!!c.text.trim() || c.imageIds.length > 0);
  });
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
  protected readonly reactionPickerPost = signal<string | null>(null);
  protected readonly reportingPost = signal<string | null>(null);
  protected readonly submittingReport = signal(false);
  protected reportCategory: PostReportCategory = 'spam';
  protected reportReason = '';
  protected readonly reportedPosts = signal<Set<string>>(new Set());
  protected readonly reactions: ReadonlyArray<{ type: ReactionType; emoji: string; label: string }> = [
    { type: 'like', emoji: '👍', label: 'Like' },
    { type: 'insightful', emoji: '💡', label: 'Insightful' },
    { type: 'celebrate', emoji: '🎉', label: 'Celebrate' },
    { type: 'support', emoji: '🙏', label: 'Support' },
    { type: 'curious', emoji: '🤔', label: 'Curious' },
  ];

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

  protected onComposed(value: ComposerValue): void {
    this.composed.set(value);
    this.onDraftInput(value.text);
  }

  protected imageUrl(id: string): string { return this.net.postImageUrl(id); }

  protected async deletePost(post: FeedItem): Promise<void> {
    if (!window.confirm('Delete this post? It is removed from every feed.')) return;
    try {
      await firstValueFrom(this.net.deletePost(post.id));
      this.posts.update(list => list.filter(p => p.id !== post.id));
      this.notify.success('Post deleted.');
    } catch { /* handled */ }
  }

  protected async publish(): Promise<void> {
    const composed = this.composed();
    const content = composed.text.trim();
    if (!this.canPost()) return;
    this.posting.set(true);
    try {
      const hashtags = [...content.matchAll(/#(\w+)/g)].map((m) => m[1]);
      const mention_ids = [...this.taggedIds()];
      const preview = this.linkPreview();
      const created = await firstValueFrom(
        this.net.createPost({
          content,
          content_html: composed.html || null,
          image_ids: composed.imageIds,
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
      this.composer()?.clear();
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

  protected reactionFor(type: ReactionType | null): { emoji: string; label: string } {
    return this.reactions.find((item) => item.type === type) ?? { emoji: '👍', label: 'React' };
  }

  protected async selectReaction(post: FeedItem, reaction: ReactionType): Promise<void> {
    const previous = post.my_reaction;
    const remove = previous === reaction;
    this.reactionPickerPost.set(null);
    // Optimistic update.
    this.patch(post.id, {
      my_reaction: remove ? null : reaction,
      like_count: post.like_count + (remove ? -1 : previous ? 0 : 1),
    });
    try {
      await firstValueFrom(remove ? this.net.unreact(post.id) : this.net.react(post.id, reaction));
    } catch {
      this.patch(post.id, { my_reaction: post.my_reaction, like_count: post.like_count });
    }
  }

  protected openReport(post: FeedItem): void {
    this.reportingPost.set(post.id);
    this.reportCategory = 'spam';
    this.reportReason = '';
  }

  protected cancelReport(): void {
    this.reportingPost.set(null);
    this.reportReason = '';
  }

  protected async submitReport(post: FeedItem): Promise<void> {
    const reason = this.reportReason.trim();
    if (reason.length < 10 || this.submittingReport()) return;
    this.submittingReport.set(true);
    try {
      const result = await firstValueFrom(this.net.reportPost(post.id, this.reportCategory, reason));
      this.reportedPosts.update((current) => new Set(current).add(post.id));
      this.reportingPost.set(null);
      this.notify.success(`Report ${result.ticket_number} sent to the Grievance Cell.`);
    } catch {
      /* handled */
    } finally {
      this.submittingReport.set(false);
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

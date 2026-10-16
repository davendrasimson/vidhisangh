import { Injectable, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { MatDialog } from '@angular/material/dialog';
import { filter, map } from 'rxjs';
import { AuthService } from '@core/auth/auth.service';
import { HELP_TOPICS, HelpTopic, topicForUrl } from './help-content';
import { HelpDialogComponent, HelpDialogData } from './help-dialog.component';

@Injectable({ providedIn: 'root' })
export class HelpService {
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly auth = inject(AuthService);
  readonly url = toSignal(this.router.events.pipe(
    filter((event): event is NavigationEnd => event instanceof NavigationEnd),
    map(event => event.urlAfterRedirects),
  ), { initialValue: this.router.url });
  readonly current = computed(() => topicForUrl(this.url()));
  readonly inWorkspace = computed(() => this.url().split(/[?#]/)[0].startsWith('/app/'));
  /** Public pages with the site header (sign-in and Help links): no separate help strip. */
  readonly onLanding = computed(() =>
    ['/', '/about', '/help', '/privacy', '/terms', '/trust'].includes(this.url().split(/[?#]/)[0].replace(/\/$/, '') || '/'));
  readonly libraryPath = computed(() => this.inWorkspace() ? '/app/help' : '/help');
  readonly tourTopics = computed(() => HELP_TOPICS.filter(topic => topic.featured &&
    (!this.auth.user() || !topic.permission || this.auth.hasPermission(topic.permission))));

  open(mode: 'help' | 'tip' | 'tour', topic?: HelpTopic): void {
    const data: HelpDialogData = {
      mode,
      topics: mode === 'tour' ? this.tourTopics() : [topic ?? this.current()],
      libraryPath: this.libraryPath(),
    };
    this.dialog.open(HelpDialogComponent, {
      data, width: '620px', maxWidth: '94vw', maxHeight: '90dvh',
      autoFocus: 'first-tabbable', restoreFocus: true, ariaLabel: mode === 'tour' ? 'Feature tour' : `${data.topics[0].title} help`,
    });
  }
}

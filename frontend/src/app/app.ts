import { HelpControlsComponent } from '@features/help/help-controls.component';
import { HelpService } from '@features/help/help.service';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ThemeService } from '@core/services/theme.service';
import { SeoService } from '@core/services/seo.service';
import { captureReferral } from '@core/services/referral-capture';

@Component({
  selector: 'app-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, HelpControlsComponent],
  template: `@if (!help.inWorkspace() && !help.onLanding()) { <div class="public-help"><app-help-controls /></div> }<router-outlet />`,
  styles: [`.public-help { display: flex; justify-content: flex-end; padding: .5rem 1rem; background: rgb(var(--vs-surface-raised)); }`],
})
export class App {
  readonly help = inject(HelpService);
  // Instantiated eagerly so the persisted theme is applied on first paint.
  private readonly theme = inject(ThemeService);
  // Per-route title, description, canonical URL and robots tag.
  private readonly seo = inject(SeoService);

  constructor() {
    // A colleague's invite link; credited when this visitor signs up. (Not during prerender.)
    if (typeof window !== 'undefined') captureReferral(window.location.search);
  }
}

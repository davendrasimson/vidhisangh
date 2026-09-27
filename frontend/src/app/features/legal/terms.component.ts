import { ChangeDetectionStrategy, Component } from '@angular/core';
import { LegalPageComponent } from './legal-page.component';
import { TERMS_MD } from './legal-text';

/** Public /terms — Terms of Service with the Data Processing Schedule. */
@Component({
  selector: 'app-terms',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LegalPageComponent],
  template: `<vs-legal-page title="Terms of Service" [markdown]="md" [showFacts]="false" />`,
})
export class TermsComponent {
  protected readonly md = TERMS_MD;
}

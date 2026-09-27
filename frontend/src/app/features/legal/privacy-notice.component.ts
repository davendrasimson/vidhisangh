import { ChangeDetectionStrategy, Component } from '@angular/core';
import { LegalPageComponent } from './legal-page.component';
import { PRIVACY_NOTICE_MD } from './legal-text';

/** Public /privacy — the DPDP s.5 notice with the live grievance officer block. */
@Component({
  selector: 'app-privacy-notice',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LegalPageComponent],
  template: `<vs-legal-page title="Privacy notice" [markdown]="md" />`,
})
export class PrivacyNoticeComponent {
  protected readonly md = PRIVACY_NOTICE_MD;
}

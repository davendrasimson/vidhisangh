import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatChipsModule } from '@angular/material/chips';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { AuthService } from '@core/auth/auth.service';
import { ProfileService } from '@core/services/profile.service';
import { NotificationService } from '@core/services/notification.service';
import { ProfileDetail, PublicationItem } from '@core/models/profile.models';

const csv = (v: string | null | undefined): string[] =>
  (v ?? '').split(',').map((s) => s.trim()).filter(Boolean);

@Component({
  selector: 'app-profile',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule, FormsModule, MatIconModule, MatButtonModule, MatFormFieldModule,
    MatInputModule, MatSlideToggleModule, MatChipsModule,
  ],
  templateUrl: './profile.component.html',
  styleUrl: './profile.component.scss',
})
export class ProfileComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly profiles = inject(ProfileService);
  private readonly notify = inject(NotificationService);
  private readonly sanitizer = inject(DomSanitizer);
  protected readonly auth = inject(AuthService);

  protected readonly qr = signal<SafeHtml | null>(null);
  protected readonly showCard = signal(false);

  protected readonly profile = signal<ProfileDetail | null>(null);
  protected readonly editing = signal(false);
  protected readonly saving = signal(false);
  // Publications are structured, so edited via a small dynamic list (not CSV).
  protected readonly pubDraft = signal<PublicationItem[]>([]);

  protected readonly user = this.auth.user;
  protected readonly initials = computed(() => {
    const n = this.user()?.full_name ?? '';
    return n.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || 'U';
  });
  protected readonly endorsements = computed(() =>
    Object.entries(this.profile()?.endorsement_summary ?? {}).sort((a, b) => b[1] - a[1]),
  );

  protected readonly form = this.fb.nonNullable.group({
    headline: [''],
    bio: [''],
    years_of_experience: [null as number | null],
    practice_areas: [''],
    courts: [''],
    languages: [''],
    city: [''],
    website: [''],
    linkedin_url: [''],
    consultation_enabled: [false],
    consultation_fee: [null as number | null],
  });

  protected readonly verifyForm = this.fb.nonNullable.group({
    enrollment_number: [''],
    bar_council: [''],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private async reload(): Promise<void> {
    try {
      this.profile.set(await firstValueFrom(this.profiles.myProfile()));
    } catch {
      /* surfaced by the error interceptor */
    }
  }

  protected enterEdit(): void {
    const p = this.profile();
    if (!p) return;
    this.form.patchValue({
      headline: p.headline ?? '',
      bio: p.bio ?? '',
      years_of_experience: p.years_of_experience,
      practice_areas: p.practice_areas.join(', '),
      courts: p.courts.join(', '),
      languages: p.languages.join(', '),
      city: p.city ?? '',
      website: p.website ?? '',
      linkedin_url: p.linkedin_url ?? '',
      consultation_enabled: p.consultation_enabled,
      consultation_fee: p.consultation_fee != null ? Number(p.consultation_fee) : null,
    });
    this.pubDraft.set((p.publications ?? []).map((pub) => ({ ...pub })));
    this.editing.set(true);
  }

  protected addPublication(): void {
    this.pubDraft.update((list) => [...list, { title: '', publisher: null, year: null, url: null }]);
  }

  protected removePublication(index: number): void {
    this.pubDraft.update((list) => list.filter((_, i) => i !== index));
  }

  protected updatePublication(index: number, field: keyof PublicationItem, value: string): void {
    const next =
      field === 'year' ? (value ? Number(value) : null) : field === 'title' ? value : value || null;
    this.pubDraft.update((list) =>
      list.map((pub, i) => (i === index ? { ...pub, [field]: next } : pub)),
    );
  }

  protected async save(): Promise<void> {
    if (this.saving()) return;
    this.saving.set(true);
    const v = this.form.getRawValue();
    try {
      const updated = await firstValueFrom(
        this.profiles.update({
          headline: v.headline || null,
          bio: v.bio || null,
          years_of_experience: v.years_of_experience,
          practice_areas: csv(v.practice_areas),
          courts: csv(v.courts),
          languages: csv(v.languages),
          city: v.city || null,
          website: v.website || null,
          linkedin_url: v.linkedin_url || null,
          consultation_enabled: v.consultation_enabled,
          consultation_fee: v.consultation_fee,
          publications: this.pubDraft().filter((p) => p.title.trim()),
        }),
      );
      this.profile.set(updated as ProfileDetail);
      await this.reload();
      this.editing.set(false);
      this.notify.success('Profile updated.');
    } catch {
      /* error interceptor shows the toast */
    } finally {
      this.saving.set(false);
    }
  }

  protected async toggleCard(): Promise<void> {
    const next = !this.showCard();
    this.showCard.set(next);
    if (next && this.qr() === null) {
      try {
        const svg = await firstValueFrom(this.profiles.qrSvg());
        this.qr.set(this.sanitizer.bypassSecurityTrustHtml(svg));
      } catch {
        /* handled */
      }
    }
  }

  protected async downloadVcard(): Promise<void> {
    try {
      const blob = await firstValueFrom(this.profiles.vcard());
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'vidhisangh-card.vcf';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* handled */
    }
  }

  protected async requestVerification(): Promise<void> {
    const v = this.verifyForm.getRawValue();
    if (!v.enrollment_number || !v.bar_council) {
      this.notify.error('Enter your enrolment number and bar council.');
      return;
    }
    try {
      await firstValueFrom(this.profiles.requestVerification(v));
      this.notify.success('Verification request submitted for review.');
      await this.reload();
    } catch {
      /* handled */
    }
  }
}

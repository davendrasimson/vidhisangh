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
import {
  EducationItem,
  EmploymentItem,
  GroupVisibility,
  MembershipItem,
  ProfileDetail,
  ProfileMasters,
  PublicationItem,
} from '@core/models/profile.models';

import { saveBlob } from '@core/platform/save-file';
import { PublicPageCardComponent } from '@shared/public-page/public-page-card.component';

const csv = (v: string | null | undefined): string[] =>
  (v ?? '').split(',').map((s) => s.trim()).filter(Boolean);

@Component({
  selector: 'app-profile',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule, FormsModule, MatIconModule, MatButtonModule, MatFormFieldModule,
    MatInputModule, MatSlideToggleModule, MatChipsModule, PublicPageCardComponent,
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
  protected readonly masters = signal<ProfileMasters | null>(null);
  protected readonly editing = signal(false);
  protected readonly saving = signal(false);
  // Publications are structured, so edited via a small dynamic list (not CSV).
  protected readonly pubDraft = signal<PublicationItem[]>([]);
  protected readonly educationDraft = signal<EducationItem[]>([]);
  protected readonly employmentDraft = signal<EmploymentItem[]>([]);
  protected readonly membershipDraft = signal<MembershipItem[]>([]);
  protected readonly selectedPracticeAreas = signal<Set<string>>(new Set());
  protected readonly selectedCourts = signal<Set<string>>(new Set());
  protected readonly selectedLanguages = signal<Set<string>>(new Set());

  protected readonly user = this.auth.user;
  protected readonly initials = computed(() => {
    const n = this.user()?.full_name ?? '';
    return n.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase() || 'U';
  });
  protected readonly endorsements = computed(() =>
    Object.entries(this.profile()?.endorsement_summary ?? {}).sort((a, b) => b[1] - a[1]),
  );
  protected readonly cities = computed(() => this.masters()?.cities_by_state[this.form.controls.state.value] ?? []);
  protected readonly isJudicial = computed(() =>
    ['judicial_officer', 'retired_judicial_officer'].includes(this.form.controls.professional_role.value),
  );

  protected readonly form = this.fb.nonNullable.group({
    headline: [''],
    bio: [''],
    professional_role: [''],
    designation: [''],
    enrollment_number: [''],
    bar_council: [''],
    year_of_enrollment: [null as number | null],
    years_of_experience: [null as number | null],
    achievements: [''],
    state: [''],
    city: [''],
    postal_code: [''],
    office_address: [''],
    professional_email: [''],
    professional_phone: [''],
    website: [''],
    linkedin_url: [''],
    judicial_court_name: [''],
    judicial_court_address: [''],
    judicial_district: [''],
    judicial_state: [''],
    consultation_enabled: [false],
    consultation_fee: [null as number | null],
    vis_about: ['everyone' as GroupVisibility],
    vis_professional: ['everyone' as GroupVisibility],
    vis_education: ['connections' as GroupVisibility],
    vis_location: ['connections' as GroupVisibility],
    vis_contact: ['none' as GroupVisibility],
    vis_judicial: ['connections' as GroupVisibility],
  });

  protected readonly verifyForm = this.fb.nonNullable.group({
    enrollment_number: [''],
    bar_council: [''],
  });

  async ngOnInit(): Promise<void> {
    try { this.masters.set(await firstValueFrom(this.profiles.masters())); } catch { /* handled */ }
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
      professional_role: p.professional_role ?? '',
      designation: p.designation ?? '',
      enrollment_number: p.enrollment_number ?? '',
      bar_council: p.bar_council ?? '',
      year_of_enrollment: p.year_of_enrollment,
      years_of_experience: p.years_of_experience,
      achievements: p.achievements.join(', '),
      state: p.state ?? '',
      city: p.city ?? '',
      postal_code: p.postal_code ?? '',
      office_address: p.office_address ?? '',
      professional_email: p.professional_email ?? '',
      professional_phone: p.professional_phone ?? '',
      website: p.website ?? '',
      linkedin_url: p.linkedin_url ?? '',
      judicial_court_name: p.judicial_court_name ?? '',
      judicial_court_address: p.judicial_court_address ?? '',
      judicial_district: p.judicial_district ?? '',
      judicial_state: p.judicial_state ?? '',
      consultation_enabled: p.consultation_enabled,
      consultation_fee: p.consultation_fee != null ? Number(p.consultation_fee) : null,
      vis_about: p.visibility_settings['about'] ?? 'everyone',
      vis_professional: p.visibility_settings['professional'] ?? 'everyone',
      vis_education: p.visibility_settings['education'] ?? 'connections',
      vis_location: p.visibility_settings['location'] ?? 'connections',
      vis_contact: p.visibility_settings['contact'] ?? 'none',
      vis_judicial: p.visibility_settings['judicial'] ?? 'connections',
    });
    this.selectedPracticeAreas.set(new Set(p.practice_areas));
    this.selectedCourts.set(new Set(p.courts));
    this.selectedLanguages.set(new Set(p.languages));
    this.educationDraft.set((p.education ?? []).map((item) => ({ ...item })));
    this.employmentDraft.set((p.employment_history ?? []).map((item) => ({ ...item })));
    this.membershipDraft.set((p.memberships ?? []).map((item) => ({ ...item })));
    this.pubDraft.set((p.publications ?? []).map((pub) => ({ ...pub })));
    this.editing.set(true);
  }

  protected addPublication(): void {
    this.pubDraft.update((list) => [...list, { title: '', publisher: null, year: null, url: null }]);
  }

  protected removePublication(index: number): void {
    this.pubDraft.update((list) => list.filter((_, i) => i !== index));
  }

  protected toggleMaster(target: 'practice' | 'courts' | 'languages', value: string): void {
    const store = target === 'practice' ? this.selectedPracticeAreas : target === 'courts' ? this.selectedCourts : this.selectedLanguages;
    store.update((current) => { const next = new Set(current); next.has(value) ? next.delete(value) : next.add(value); return next; });
  }
  protected selected(target: 'practice' | 'courts' | 'languages', value: string): boolean {
    const store = target === 'practice' ? this.selectedPracticeAreas : target === 'courts' ? this.selectedCourts : this.selectedLanguages;
    return store().has(value);
  }
  protected addEducation(): void { this.educationDraft.update((items) => [...items, { institution: '', level: 'undergraduate', degree: 'llb_3', field_of_study: 'Law', start_year: null, year: null }]); }
  protected removeEducation(index: number): void { this.educationDraft.update((items) => items.filter((_, i) => i !== index)); }
  protected updateEducation(index: number, field: keyof EducationItem, value: string | number | null): void {
    const numeric = ['start_year', 'year'].includes(field) && value ? Number(value) : value;
    this.educationDraft.update((items) => items.map((item, i) => i === index ? { ...item, [field]: numeric || null } : item));
  }
  protected addEmployment(): void { this.employmentDraft.update((items) => [...items, { organisation: '', designation: '', from_year: null, to_year: null, current: false }]); }
  protected removeEmployment(index: number): void { this.employmentDraft.update((items) => items.filter((_, i) => i !== index)); }
  protected updateEmployment(index: number, field: keyof EmploymentItem, value: string | number | boolean | null): void { this.employmentDraft.update((items) => items.map((item, i) => i === index ? { ...item, [field]: value } : item)); }
  protected addMembership(): void { this.membershipDraft.update((items) => [...items, { organisation: '', membership_number: '', year: null }]); }
  protected removeMembership(index: number): void { this.membershipDraft.update((items) => items.filter((_, i) => i !== index)); }
  protected updateMembership(index: number, field: keyof MembershipItem, value: string | number | null): void { this.membershipDraft.update((items) => items.map((item, i) => i === index ? { ...item, [field]: value } : item)); }
  protected masterLabel(items: { value: string; label: string }[], value: string | null | undefined): string { return items.find((item) => item.value === value)?.label ?? value ?? ''; }

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
          professional_role: v.professional_role || null,
          designation: v.designation || null,
          enrollment_number: v.enrollment_number || null,
          bar_council: v.bar_council || null,
          year_of_enrollment: v.year_of_enrollment,
          years_of_experience: v.years_of_experience,
          practice_areas: [...this.selectedPracticeAreas()],
          courts: [...this.selectedCourts()],
          languages: [...this.selectedLanguages()],
          achievements: csv(v.achievements),
          state: v.state || null,
          city: v.city || null,
          postal_code: v.postal_code || null,
          office_address: v.office_address || null,
          professional_email: v.professional_email || null,
          professional_phone: v.professional_phone || null,
          website: v.website || null,
          linkedin_url: v.linkedin_url || null,
          judicial_court_name: v.judicial_court_name || null,
          judicial_court_address: v.judicial_court_address || null,
          judicial_district: v.judicial_district || null,
          judicial_state: v.judicial_state || null,
          consultation_enabled: v.consultation_enabled,
          consultation_fee: v.consultation_fee,
          publications: this.pubDraft().filter((p) => p.title.trim()),
          education: this.educationDraft().filter((e) => e.institution.trim()),
          employment_history: this.employmentDraft().filter((e) => e.organisation.trim()),
          memberships: this.membershipDraft().filter((e) => e.organisation.trim()),
          visibility_settings: {
            about: v.vis_about, professional: v.vis_professional, education: v.vis_education,
            location: v.vis_location, contact: v.vis_contact, judicial: v.vis_judicial,
          },
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
      await saveBlob(blob, 'vidhisangh-card.vcf');
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

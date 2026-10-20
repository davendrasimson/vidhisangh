import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { environment } from '@env/environment';
import { problemMessage } from '@core/http/problem-message';
import { NotificationService } from '@core/services/notification.service';

interface PublicPage { enabled: boolean; handle: string | null; url: string | null }

/**
 * "Public profile page": vidhisangh.com/in/<handle>/, open to search engines.
 * A separate opt-in from the in-app directory; shows only the profile
 * sections set to "Everyone", never contact details.
 */
@Component({
  selector: 'vs-public-page-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatButtonModule, MatIconModule, MatSlideToggleModule],
  template: `
    <section class="rounded-card bg-surface-raised border border-line shadow-card p-5 mb-5 grid gap-3">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="flex-1 min-w-[14rem]">
          <h2 class="font-semibold">Public profile page</h2>
          <p class="text-sm text-content-muted">
            A page at vidhisangh.com/in/your-name that anyone can open and search engines (Google, Bing) can list, so clients and colleagues
            who search for you find it. It shows only the profile sections you set to “Everyone” — never your phone, email or address.
            Off unless you turn it on; you can withdraw it at any time.
          </p>
        </div>
        @if (page(); as p) {
          <mat-slide-toggle [checked]="p.enabled" [disabled]="busy()" (change)="save($event.checked)" aria-label="Public profile page">
            {{ p.enabled ? 'Published' : 'Off' }}
          </mat-slide-toggle>
        }
      </div>
      @if (error()) { <p role="alert" class="text-sm text-danger">{{ error() }}</p> }
      @if (page(); as p) {
        @if (p.enabled && p.url) {
          <div class="flex flex-wrap items-center gap-2">
            <a class="text-brand underline break-all" [href]="p.url" target="_blank" rel="noopener">{{ p.url }}</a>
          </div>
          <div class="flex flex-wrap gap-2">
            <a mat-flat-button class="!bg-[#1f9d55] !text-white" [href]="whatsapp()" target="_blank" rel="noopener">
              <mat-icon class="material-icons-outlined">share</mat-icon> Share on WhatsApp
            </a>
            <button mat-stroked-button type="button" (click)="copy(p.url)"><mat-icon class="material-icons-outlined">content_copy</mat-icon> Copy link</button>
          </div>
          <form class="flex flex-wrap items-end gap-2" (ngSubmit)="rename()">
            <label class="text-sm grid gap-1">Address
              <span class="flex items-center gap-1"><span class="text-content-muted">vidhisangh.com/in/</span>
                <input class="vs-input w-48" name="handle" [(ngModel)]="handle" maxlength="40" pattern="[a-z0-9]+(-[a-z0-9]+)*" aria-label="Page address" />
              </span>
            </label>
            <button mat-stroked-button type="submit" [disabled]="busy() || !handle || handle === p.handle">Change address</button>
          </form>
        }
      }
    </section>
  `,
})
export class PublicPageCardComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly notify = inject(NotificationService);
  private readonly api = `${environment.apiBaseUrl}/network/me/public-page`;
  protected readonly page = signal<PublicPage | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected handle = '';
  protected readonly whatsapp = computed(() => {
    const url = this.page()?.url;
    return url ? `https://wa.me/?text=${encodeURIComponent(`My profile on VidhiSangh: ${url}`)}` : '';
  });

  async ngOnInit(): Promise<void> {
    try { this.set(await firstValueFrom(this.http.get<PublicPage>(this.api))); } catch { /* toast shown */ }
  }

  private set(p: PublicPage): void {
    this.page.set(p);
    this.handle = p.handle ?? '';
  }

  protected async save(enabled: boolean, handle?: string): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.set(await firstValueFrom(this.http.put<PublicPage>(this.api, handle ? { enabled, handle } : { enabled })));
      this.notify.success(enabled ? 'Your public profile page is live.' : 'Your public profile page is withdrawn.');
    } catch (err) {
      this.error.set(problemMessage(err, 'Could not save. Please try again.'));
      const current = this.page();
      if (current) this.page.set({ ...current });  // reset the toggle
    } finally { this.busy.set(false); }
  }

  protected rename(): Promise<void> {
    return this.save(true, this.handle.trim().toLowerCase());
  }

  protected async copy(url: string): Promise<void> {
    try { await navigator.clipboard.writeText(url); this.notify.success('Link copied.'); } catch { /* clipboard unavailable */ }
  }
}

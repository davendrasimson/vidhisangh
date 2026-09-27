import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { firstValueFrom } from 'rxjs';
import { ClientsService } from '@core/services/clients.service';
import { ClientKind, ClientSummary } from '@core/models/clients.models';

export interface ClientChoice {
  /** A client-master id, or null when the user typed a name instead. */
  id: string | null;
  name: string;
}

/**
 * Pick a client from the client master — search as you type, or add a new
 * client on the spot without leaving the form. Typing a name without picking
 * one is allowed too (quick intake): the choice then has `id: null`.
 */
@Component({
  selector: 'vs-client-picker',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatButtonModule, MatIconModule],
  template: `
    @if (selected(); as c) {
      <div class="flex items-center gap-2 rounded-lg border border-line bg-surface-sunken px-3 py-2">
        <mat-icon class="material-icons-outlined text-base text-brand">badge</mat-icon>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium truncate">{{ c.name }}</p>
          @if (c.id) {
            <a class="text-xs text-brand" [routerLink]="['/app/clients', c.id]">Open client record</a>
          } @else {
            <p class="text-xs text-content-muted">Typed name — not linked to the client master</p>
          }
        </div>
        @if (!disabled()) {
          <button mat-button type="button" (click)="clear()">Change</button>
        }
      </div>
    } @else {
      <div class="relative">
        <div class="flex gap-2">
          <input class="vs-input flex-1" [ngModel]="query()" (ngModelChange)="onQuery($event)" (focus)="open.set(true)"
                 (blur)="onBlur()" [placeholder]="placeholder()" autocomplete="off" maxlength="200" />
          <button mat-stroked-button type="button" (click)="startNew()">
            <mat-icon class="material-icons-outlined">person_add</mat-icon> New client
          </button>
        </div>
        @if (open() && (results().length || query().trim())) {
          <ul class="absolute z-20 mt-1 w-full max-h-64 overflow-auto rounded-lg border border-line bg-surface-raised shadow-card text-sm">
            @for (r of results(); track r.id) {
              <li>
                <button type="button" class="w-full text-left px-3 py-2 hover:bg-surface-sunken" (mousedown)="pick(r)">
                  <span class="font-medium">{{ r.display_name }}</span>
                  <span class="text-xs text-content-muted ml-2">{{ r.kind === 'business' ? 'Business' : 'Individual' }}@if (r.city) { · {{ r.city }} }@if (r.pan) { · {{ r.pan }} }</span>
                </button>
              </li>
            } @empty {
              @if (query().trim()) {
                <li class="px-3 py-2 text-content-muted">{{ searching() ? 'Searching…' : 'No client matches. Add one, or use the name as typed.' }}</li>
              }
            }
            @if (query().trim()) {
              <li class="border-t border-line">
                <button type="button" class="w-full text-left px-3 py-2 hover:bg-surface-sunken" (mousedown)="useTyped()">
                  Use “{{ query().trim() }}” as typed (no client record)
                </button>
              </li>
            }
          </ul>
        }
      </div>
    }

    @if (creating()) {
      <div class="mt-2 rounded-lg border border-brand/40 bg-surface-raised p-3">
        <p class="text-sm font-medium mb-2">New client</p>
        <div class="grid gap-2 sm:grid-cols-4">
          <select class="vs-input" [(ngModel)]="draft.kind">
            <option value="individual">Individual</option>
            <option value="business">Business</option>
          </select>
          <input class="vs-input sm:col-span-3" [(ngModel)]="draft.display_name" [placeholder]="draft.kind === 'business' ? 'Legal name of the business' : 'Full name'" maxlength="300" />
          <input class="vs-input sm:col-span-2" type="email" [(ngModel)]="draft.email" placeholder="Email (optional)" />
          <input class="vs-input sm:col-span-2" [(ngModel)]="draft.mobile" placeholder="Mobile (optional)" maxlength="10" />
        </div>
        <p class="text-xs text-content-muted mt-2">Tax defaults, consent and KYC can be completed later on the client record.</p>
        <div class="flex justify-end gap-2 mt-2">
          <button mat-button type="button" (click)="creating.set(false)">Cancel</button>
          <button mat-flat-button color="primary" type="button" [disabled]="!draft.display_name.trim() || saving()" (click)="createClient()">
            {{ saving() ? 'Adding…' : 'Add & select' }}
          </button>
        </div>
      </div>
    }
  `,
})
export class VsClientPickerComponent {
  private readonly clients = inject(ClientsService);

  /** Initial value (e.g. the matter's current client). */
  readonly value = input<ClientChoice | null>(null);
  readonly placeholder = input('Search clients by name, PAN, GSTIN, email…');
  readonly disabled = input(false);
  readonly selected = signal<ClientChoice | null>(null);
  readonly changed = output<ClientChoice | null>();

  protected readonly query = signal('');
  protected readonly open = signal(false);
  protected readonly results = signal<ClientSummary[]>([]);
  protected readonly searching = signal(false);
  protected readonly creating = signal(false);
  protected readonly saving = signal(false);
  protected draft = { kind: 'individual' as ClientKind, display_name: '', email: '', mobile: '' };
  protected readonly hasValue = computed(() => this.selected() !== null);
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    effect(() => this.selected.set(this.value()));
  }

  protected onQuery(q: string): void {
    this.query.set(q);
    this.open.set(true);
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.search(), 250);
  }

  private async search(): Promise<void> {
    const q = this.query().trim();
    this.searching.set(true);
    try {
      this.results.set(await firstValueFrom(this.clients.list({ q: q || undefined, status: 'active' })));
    } catch {
      this.results.set([]);
    } finally {
      this.searching.set(false);
    }
  }

  protected onBlur(): void {
    // Let a mousedown on a result land before the list closes.
    setTimeout(() => this.open.set(false), 150);
  }

  protected pick(c: ClientSummary): void {
    this.set({ id: c.id, name: c.display_name });
  }

  protected useTyped(): void {
    const name = this.query().trim();
    if (name) this.set({ id: null, name });
  }

  protected clear(): void {
    this.selected.set(null);
    this.query.set('');
    this.changed.emit(null);
  }

  protected startNew(): void {
    this.draft = { kind: 'individual', display_name: this.query().trim(), email: '', mobile: '' };
    this.creating.set(true);
    this.open.set(false);
  }

  protected async createClient(): Promise<void> {
    if (this.saving()) return;
    this.saving.set(true);
    try {
      const created = await firstValueFrom(this.clients.create({
        kind: this.draft.kind,
        display_name: this.draft.display_name.trim(),
        legal_name: this.draft.kind === 'business' ? this.draft.display_name.trim() : null,
        email: this.draft.email.trim() || null,
        mobile: this.draft.mobile.trim() || null,
      }));
      this.creating.set(false);
      this.set({ id: created.id, name: created.display_name });
    } catch {
      /* surfaced by the interceptor */
    } finally {
      this.saving.set(false);
    }
  }

  private set(choice: ClientChoice): void {
    this.selected.set(choice);
    this.open.set(false);
    this.changed.emit(choice);
  }
}

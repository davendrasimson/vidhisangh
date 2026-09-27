import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { firstValueFrom } from 'rxjs';
import { RatesService } from '@core/services/rates.service';
import { NotificationService } from '@core/services/notification.service';
import { RATE_BASIS_LABELS, RateBasis, RateCard } from '@core/models/matters.models';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';

/** Counsel rate cards — what each member of the firm charges, by basis, over time. */
@Component({
  selector: 'app-counsel-rates',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatButtonModule, MatIconModule, VsDateInputComponent],
  template: `
    <div class="mx-auto w-full">
      <a routerLink="/app/settings" class="text-sm text-content-muted inline-flex items-center gap-1 mb-3">
        <mat-icon class="material-icons-outlined text-base">arrow_back</mat-icon> Settings
      </a>
      <h1 class="vs-display text-3xl font-semibold text-content">Counsel rates</h1>
      <p class="text-sm text-content-muted mt-0.5 mb-5">
        Each person's standard charges by basis — per hour, per hearing, per day, per matter, per drafting, or a monthly retainer.
        A new rate for the same basis supersedes the open one. A matter's team row can override these for that matter alone.
      </p>

      @if (loading()) {
        <p class="text-content-muted">Loading…</p>
      } @else {
        <div class="grid gap-4">
          @for (card of cards(); track card.user_id) {
            <section class="rounded-card bg-surface-raised border border-line shadow-card p-4">
              <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div>
                  <h2 class="font-semibold">{{ card.full_name }} @if (!card.is_active) { <span class="vs-chip text-warning ml-1">Inactive</span> }</h2>
                  <p class="text-xs text-content-muted">{{ card.email }}</p>
                </div>
                <button mat-stroked-button (click)="startAdd(card.user_id)">
                  <mat-icon class="material-icons-outlined">add</mat-icon> Add rate
                </button>
              </div>

              @if (card.rates.length) {
                <table class="w-full text-sm">
                  <thead class="text-xs uppercase tracking-wide text-content-muted">
                    <tr><th class="text-left py-1">Basis</th><th class="text-right py-1">Amount</th><th class="text-left py-1 pl-4">From</th><th class="text-left py-1">To</th><th class="text-left py-1">Notes</th><th></th></tr>
                  </thead>
                  <tbody>
                    @for (r of card.rates; track r.id) {
                      <tr class="border-t border-line" [class.text-content-muted]="!r.is_current">
                        <td class="py-1.5">{{ basisLabels[r.basis] }}@if (r.is_current) { <span class="vs-chip vs-chip-selected ml-1">Current</span> }</td>
                        <td class="py-1.5 text-right font-mono">₹{{ r.amount }}</td>
                        <td class="py-1.5 pl-4">{{ r.effective_from | date }}</td>
                        <td class="py-1.5">{{ r.effective_to ? (r.effective_to | date) : 'open' }}</td>
                        <td class="py-1.5 text-xs">{{ r.notes }}</td>
                        <td class="py-1.5 text-right">
                          @if (!r.effective_to) { <button mat-button (click)="endToday(r.id)">End today</button> }
                          <button mat-icon-button (click)="remove(r.id)" aria-label="Remove rate"><mat-icon class="material-icons-outlined text-base">delete</mat-icon></button>
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              } @else {
                <p class="text-sm text-content-muted">No rates yet.</p>
              }

              @if (adding() === card.user_id) {
                <div class="grid gap-2 sm:grid-cols-5 mt-3 pt-3 border-t border-line">
                  <select class="vs-input" [(ngModel)]="draft.basis">
                    @for (b of basisKeys; track b) { <option [value]="b">{{ basisLabels[b] }}</option> }
                  </select>
                  <input class="vs-input" type="number" min="0" step="1" [(ngModel)]="draft.amount" placeholder="Amount (₹)" />
                  <vs-date-input [(ngModel)]="draft.effective_from" />
                  <input class="vs-input" [(ngModel)]="draft.notes" placeholder="Notes (optional)" />
                  <div class="flex gap-1 justify-end">
                    <button mat-button (click)="adding.set(null)">Cancel</button>
                    <button mat-flat-button color="primary" [disabled]="!draft.amount || saving()" (click)="save(card.user_id)">Save</button>
                  </div>
                </div>
              }
            </section>
          }
        </div>
      }
    </div>
  `,
})
export class CounselRatesComponent implements OnInit {
  private readonly rates = inject(RatesService);
  private readonly notify = inject(NotificationService);

  protected readonly cards = signal<RateCard[]>([]);
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly adding = signal<string | null>(null);
  protected readonly basisLabels = RATE_BASIS_LABELS;
  protected readonly basisKeys = Object.keys(RATE_BASIS_LABELS) as RateBasis[];
  protected draft = { basis: 'hourly' as RateBasis, amount: '' as string | number, effective_from: '', notes: '' };

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.loading.set(true);
    try {
      this.cards.set(await firstValueFrom(this.rates.cards()));
    } catch { /* handled */ } finally { this.loading.set(false); }
  }

  protected startAdd(userId: string): void {
    this.draft = { basis: 'hourly', amount: '', effective_from: '', notes: '' };
    this.adding.set(userId);
  }

  protected async save(userId: string): Promise<void> {
    if (this.saving()) return;
    this.saving.set(true);
    try {
      await firstValueFrom(this.rates.create({
        user_id: userId, basis: this.draft.basis, amount: Number(this.draft.amount),
        effective_from: this.draft.effective_from || null, notes: this.draft.notes.trim() || null,
      }));
      this.adding.set(null);
      this.notify.success('Rate saved.');
      await this.reload();
    } catch { /* handled */ } finally { this.saving.set(false); }
  }

  protected async endToday(id: string): Promise<void> {
    try {
      await firstValueFrom(this.rates.update(id, { effective_to: new Date().toISOString().slice(0, 10) }));
      await this.reload();
    } catch { /* handled */ }
  }

  protected async remove(id: string): Promise<void> {
    try {
      await firstValueFrom(this.rates.remove(id));
      await this.reload();
    } catch { /* handled */ }
  }
}

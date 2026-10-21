import { ChangeDetectionStrategy, Component, ElementRef, HostListener, effect, input, output, signal, viewChild } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/**
 * Full-screen photo viewer: swipe (or ← / →) between photos, Esc or ✕ to close.
 *   <vs-photo-viewer [photos]="urls" [start]="i" (closed)="viewer.set(null)" />
 */
@Component({
  selector: 'vs-photo-viewer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <div #dialog class="fixed inset-0 z-[1000] bg-black/95 flex items-center justify-center select-none outline-none"
         role="dialog" aria-modal="true" aria-label="Photo viewer" tabindex="-1"
         (pointerdown)="down($event)" (pointerup)="up($event)" (click)="backdrop($event)">
      <img class="max-h-full max-w-full object-contain touch-none" [src]="photos()[index()]" [alt]="'Photo ' + (index() + 1) + ' of ' + photos().length" draggable="false" />
      <button type="button" class="absolute top-3 right-3 h-11 w-11 grid place-items-center rounded-full bg-white/15 text-white" (click)="closed.emit()" aria-label="Close photo viewer">
        <mat-icon>close</mat-icon>
      </button>
      @if (photos().length > 1) {
        <button type="button" class="absolute left-2 top-1/2 -translate-y-1/2 h-11 w-11 grid place-items-center rounded-full bg-white/15 text-white disabled:opacity-30" [disabled]="index() === 0" (click)="go(-1)" aria-label="Previous photo"><mat-icon>chevron_left</mat-icon></button>
        <button type="button" class="absolute right-2 top-1/2 -translate-y-1/2 h-11 w-11 grid place-items-center rounded-full bg-white/15 text-white disabled:opacity-30" [disabled]="index() === photos().length - 1" (click)="go(1)" aria-label="Next photo"><mat-icon>chevron_right</mat-icon></button>
        <p class="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/80 text-sm" aria-live="polite">{{ index() + 1 }} of {{ photos().length }}</p>
      }
    </div>
  `,
})
export class PhotoViewerComponent {
  readonly photos = input.required<string[]>();
  readonly start = input(0);
  readonly closed = output<void>();
  protected readonly index = signal(0);
  private readonly dialog = viewChild.required<ElementRef<HTMLElement>>('dialog');
  private startX: number | null = null;

  constructor() {
    effect(() => {
      this.index.set(Math.min(Math.max(this.start(), 0), this.photos().length - 1));
      queueMicrotask(() => this.dialog().nativeElement.focus());
    });
  }

  protected go(step: number): void {
    this.index.set(Math.min(Math.max(this.index() + step, 0), this.photos().length - 1));
  }

  @HostListener('document:keydown', ['$event'])
  protected key(e: KeyboardEvent): void {
    if (e.key === 'Escape') this.closed.emit();
    else if (e.key === 'ArrowRight') this.go(1);
    else if (e.key === 'ArrowLeft') this.go(-1);
  }

  protected down(e: PointerEvent): void { this.startX = e.clientX; }

  protected up(e: PointerEvent): void {
    if (this.startX === null) return;
    const dx = e.clientX - this.startX;
    this.startX = null;
    if (Math.abs(dx) > 50) this.go(dx < 0 ? 1 : -1);
  }

  /** A tap on the dark area (not the photo or a button) closes. */
  protected backdrop(e: MouseEvent): void {
    if (e.target === e.currentTarget) this.closed.emit();
  }
}

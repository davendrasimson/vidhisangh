import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { HelpTopic } from './help-content';

export interface HelpDialogData {
  mode: 'help' | 'tip' | 'tour';
  topics: HelpTopic[];
  libraryPath: string;
}

@Component({
  selector: 'app-help-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatDialogModule, MatButtonModule, MatIconModule, RouterLink],
  template: `
    <h2 mat-dialog-title><mat-icon aria-hidden="true">{{ data.mode === 'tip' ? 'lightbulb' : 'help_outline' }}</mat-icon>
      {{ data.mode === 'tour' ? 'Feature tour' : data.mode === 'tip' ? 'Did you know?' : 'Page help' }}</h2>
    <mat-dialog-content>
      <div aria-live="polite" aria-atomic="true">
        @if (data.mode === 'tour') { <p>Step {{ index() + 1 }} of {{ data.topics.length }}</p> }
        <h3>{{ topic().title }}</h3>
        <p>{{ topic().summary }}</p>
        @if (data.mode !== 'tip') {
          <ol>@for (step of topic().steps; track $index) { <li>{{ step }}</li> }</ol>
        }
        <aside><strong>Try this:</strong> {{ topic().tip }}</aside>
      </div>
      <p class="availability">Actions depend on your role, subscription and configured services.</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      @if (data.mode === 'tour') {
        <button mat-button (click)="index.set(index() - 1)" [disabled]="index() === 0">Back</button>
        @if (index() < data.topics.length - 1) {
          <button mat-flat-button (click)="index.set(index() + 1)">Next</button>
        } @else { <button mat-flat-button mat-dialog-close>Finish tour</button> }
      } @else {
        <a mat-button [routerLink]="data.libraryPath" [queryParams]="{ topic: topic().id }" mat-dialog-close>Read full guide</a>
      }
      <button mat-button mat-dialog-close>{{ data.mode === 'tour' ? 'Close tour' : 'Close' }}</button>
    </mat-dialog-actions>
  `,
  styles: [`
    h2 { display: flex; align-items: center; gap: .6rem; }
    h3 { font-size: 1.2rem; font-weight: 600; margin: .5rem 0; }
    p, li { line-height: 1.65; } ol { padding-left: 1.4rem; list-style: decimal; }
    li { margin: .65rem 0; }
    aside { border-left: 4px solid rgb(var(--vs-brand)); padding: .8rem; margin-top: 1rem; }
    .availability { font-size: .8rem; margin-top: 1rem; }
  `],
})
export class HelpDialogComponent {
  readonly data = inject<HelpDialogData>(MAT_DIALOG_DATA);
  readonly index = signal(0);
  readonly topic = () => this.data.topics[this.index()];
}

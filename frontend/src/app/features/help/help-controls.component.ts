import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { HelpService } from './help.service';

@Component({
  selector: 'app-help-controls',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    <button mat-stroked-button (click)="help.open('help')" [attr.aria-label]="'Help for ' + help.current().title" matTooltip="Help for this page">
      <mat-icon aria-hidden="true">help_outline</mat-icon>Help
    </button>
    <button mat-icon-button (click)="help.open('tip')" [attr.aria-label]="'Tips for ' + help.current().title" matTooltip="What else can I do here?" class="bulb">
      <mat-icon aria-hidden="true">lightbulb</mat-icon>
    </button>
  `,
  styles: [`:host { display: inline-flex; align-items: center; flex-shrink: 0; gap: 2px; } .bulb { color: #946000; } :host-context(.dark) .bulb { color: #ffd166; }`],
})
export class HelpControlsComponent { readonly help = inject(HelpService); }

import { Injectable, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

/** Thin wrapper over MatSnackBar for consistent, themed toasts. */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly snackBar = inject(MatSnackBar);

  success(message: string): void {
    this.snackBar.open(message, 'Dismiss', {
      duration: 4000,
      panelClass: 'vs-snack-success',
      horizontalPosition: 'end',
    });
  }

  error(message: string): void {
    this.snackBar.open(message, 'Dismiss', {
      duration: 6000,
      panelClass: 'vs-snack-error',
      horizontalPosition: 'end',
    });
  }

  info(message: string): void {
    this.snackBar.open(message, 'Dismiss', { duration: 4000, horizontalPosition: 'end' });
  }
}

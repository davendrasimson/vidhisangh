import { Injectable, inject, signal } from '@angular/core';
import { AuthService } from '@core/auth/auth.service';
import { NotificationService } from '@core/services/notification.service';

@Injectable({ providedIn: 'root' })
export class KnowledgeBookmarks {
  private readonly auth = inject(AuthService);
  private readonly notify = inject(NotificationService);
  private readonly revision = signal(0);

  private key(): string {
    const user = this.auth.user();
    return `vs-knowledge-bookmarks:${user?.tenant_id}:${user?.id}`;
  }

  private read(): string[] {
    this.revision();
    try {
      const value: unknown = JSON.parse(localStorage.getItem(this.key()) ?? '[]');
      return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : [];
    } catch { return []; }
  }

  has(id: string): boolean { return this.read().includes(id); }

  toggle(id: string): void {
    const current = this.read();
    try {
      localStorage.setItem(this.key(), JSON.stringify(current.includes(id) ? current.filter((i) => i !== id) : [...current, id]));
      this.revision.update((v) => v + 1);
    } catch { this.notify.error('Bookmarks could not be saved in this browser.'); }
  }
}

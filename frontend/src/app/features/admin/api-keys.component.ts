import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { AdminService } from '@core/services/admin.service';
import { ApiKey } from '@core/models/api-key.models';

@Component({
  selector: 'app-api-keys',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, MatButtonModule],
  templateUrl: './api-keys.component.html',
})
export class ApiKeysComponent implements OnInit {
  private readonly admin = inject(AdminService);

  protected readonly keys = signal<ApiKey[]>([]);
  protected readonly scopes = signal<string[]>([]);
  protected readonly loading = signal(true);

  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected readonly busy = signal<string | null>(null);
  protected readonly newKey = signal<string | null>(null);

  protected name = '';
  protected scopeFilter = '';
  protected selected = new Set<string>();

  protected readonly filteredScopes = computed(() => {
    const q = this._filter().toLowerCase();
    return this.scopes().filter((s) => s.toLowerCase().includes(q));
  });
  // scopeFilter mirrored into a signal for the computed above.
  private readonly _filter = signal('');
  protected onFilter(v: string): void {
    this.scopeFilter = v;
    this._filter.set(v);
  }

  async ngOnInit(): Promise<void> {
    await Promise.all([this.load(), this.loadScopes()]);
    this.loading.set(false);
  }

  private async load(): Promise<void> {
    this.keys.set(await firstValueFrom(this.admin.apiKeys()));
  }

  private async loadScopes(): Promise<void> {
    try {
      this.scopes.set(await firstValueFrom(this.admin.apiKeyScopes()));
    } catch {
      /* handled */
    }
  }

  protected toggle(scope: string): void {
    this.selected.has(scope) ? this.selected.delete(scope) : this.selected.add(scope);
  }

  protected async submit(): Promise<void> {
    if (!this.name.trim() || this.selected.size === 0 || this.saving()) return;
    this.saving.set(true);
    try {
      const created = await firstValueFrom(
        this.admin.createApiKey({ name: this.name.trim(), scopes: [...this.selected] }),
      );
      this.newKey.set(created.key);
      this.name = '';
      this.selected = new Set();
      this.showForm.set(false);
      await this.load();
    } catch {
      /* handled */
    } finally {
      this.saving.set(false);
    }
  }

  protected async revoke(k: ApiKey): Promise<void> {
    this.busy.set(k.id);
    try {
      await firstValueFrom(this.admin.revokeApiKey(k.id));
      this.keys.update((list) => list.filter((x) => x.id !== k.id));
    } catch {
      /* handled */
    } finally {
      this.busy.set(null);
    }
  }
}

import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { WebhookService } from '@core/services/webhook.service';
import { NotificationService } from '@core/services/notification.service';
import { EventType, Webhook, WebhookDelivery } from '@core/models/webhook.models';

@Component({
  selector: 'app-webhooks',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, MatButtonModule, MatSlideToggleModule],
  templateUrl: './webhooks.component.html',
})
export class WebhooksComponent implements OnInit {
  private readonly webhooks = inject(WebhookService);
  private readonly notify = inject(NotificationService);

  protected readonly items = signal<Webhook[]>([]);
  protected readonly events = signal<EventType[]>([]);
  protected readonly loading = signal(true);

  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected form = this.blank();
  protected readonly newSecret = signal<string | null>(null);

  protected readonly deliveries = signal<Record<string, WebhookDelivery[] | undefined>>({});
  protected readonly busy = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    await Promise.all([this.load(), this.loadEvents()]);
    this.loading.set(false);
  }

  private async load(): Promise<void> {
    this.items.set(await firstValueFrom(this.webhooks.list()));
  }

  private async loadEvents(): Promise<void> {
    this.events.set(await firstValueFrom(this.webhooks.events()));
  }

  protected toggleEvent(key: string): void {
    const set = new Set(this.form.event_types);
    set.has(key) ? set.delete(key) : set.add(key);
    this.form.event_types = [...set];
  }

  protected async submit(): Promise<void> {
    if (!this.form.url.trim() || this.form.event_types.length === 0 || this.saving()) return;
    this.saving.set(true);
    try {
      const created = await firstValueFrom(
        this.webhooks.create({
          url: this.form.url.trim(),
          description: this.form.description.trim() || null,
          event_types: this.form.event_types,
        }),
      );
      this.newSecret.set(created.secret);
      this.form = this.blank();
      this.showForm.set(false);
      await this.load();
    } catch {
      /* handled */
    } finally {
      this.saving.set(false);
    }
  }

  protected async toggleActive(w: Webhook, active: boolean): Promise<void> {
    this.busy.set(w.id);
    try {
      const updated = await firstValueFrom(this.webhooks.update(w.id, { is_active: active }));
      this.items.update((list) => list.map((x) => (x.id === w.id ? updated : x)));
    } catch {
      /* handled */
    } finally {
      this.busy.set(null);
    }
  }

  protected async sendTest(w: Webhook): Promise<void> {
    this.busy.set(w.id);
    try {
      const d = await firstValueFrom(this.webhooks.test(w.id));
      this.notify.success(`Test event ${d.status === 'success' ? 'delivered' : 'failed'} (${d.status_code ?? '—'}).`);
      if (this.deliveries()[w.id] !== undefined) await this.viewDeliveries(w, true);
    } catch {
      /* handled */
    } finally {
      this.busy.set(null);
    }
  }

  protected async viewDeliveries(w: Webhook, force = false): Promise<void> {
    if (!force && this.deliveries()[w.id] !== undefined) {
      this.deliveries.set({ ...this.deliveries(), [w.id]: undefined });
      return;
    }
    const list = await firstValueFrom(this.webhooks.deliveries(w.id));
    this.deliveries.set({ ...this.deliveries(), [w.id]: list });
  }

  protected async remove(w: Webhook): Promise<void> {
    this.busy.set(w.id);
    try {
      await firstValueFrom(this.webhooks.remove(w.id));
      this.items.update((list) => list.filter((x) => x.id !== w.id));
    } catch {
      /* handled */
    } finally {
      this.busy.set(null);
    }
  }

  private blank(): { url: string; description: string; event_types: string[] } {
    return { url: '', description: '', event_types: [] };
  }
}

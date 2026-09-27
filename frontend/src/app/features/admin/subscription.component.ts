import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { PlanService } from '@core/services/plan.service';
import { NotificationService } from '@core/services/notification.service';
import { Plan, PlanTier, Subscription } from '@core/models/plan.models';

@Component({
  selector: 'app-subscription',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, MatButtonModule],
  templateUrl: './subscription.component.html',
})
export class SubscriptionComponent implements OnInit {
  private readonly plans = inject(PlanService);
  private readonly notify = inject(NotificationService);

  protected readonly catalog = signal<Plan[]>([]);
  protected readonly sub = signal<Subscription | null>(null);
  protected readonly loading = signal(true);
  protected readonly changing = signal<PlanTier | null>(null);

  protected readonly usersLimit = computed(() => this.sub()?.plan.max_users);
  protected readonly mattersLimit = computed(() => this.sub()?.plan.max_matters);

  async ngOnInit(): Promise<void> {
    await this.refresh();
    this.loading.set(false);
  }

  private async refresh(): Promise<void> {
    const [catalog, sub] = await Promise.all([
      firstValueFrom(this.plans.plans()),
      firstValueFrom(this.plans.subscription()),
    ]);
    this.catalog.set(catalog);
    this.sub.set(sub);
  }

  protected price(p: Plan): string {
    if (p.price_inr === null) return 'Custom';
    if (p.price_inr === 0) return 'Free';
    return `₹${p.price_inr.toLocaleString('en-IN')}/mo`;
  }

  protected limit(v: number | null): string {
    return v === null ? 'Unlimited' : `${v}`;
  }

  protected async choose(p: Plan): Promise<void> {
    if (p.is_current || this.changing()) return;
    this.changing.set(p.tier);
    try {
      this.sub.set(await firstValueFrom(this.plans.changePlan(p.tier)));
      this.catalog.set(await firstValueFrom(this.plans.plans()));
      this.notify.success(`Switched to the ${p.name} plan.`);
    } catch {
      /* handled */
    } finally {
      this.changing.set(null);
    }
  }
}

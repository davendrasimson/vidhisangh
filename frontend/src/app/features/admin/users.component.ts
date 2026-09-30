import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AdminService } from '@core/services/admin.service';
import { AuthService } from '@core/auth/auth.service';
import { NotificationService } from '@core/services/notification.service';
import { Role, User } from '@core/models/auth.models';

@Component({
  selector: 'app-admin-users',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, MatButtonModule, MatTooltipModule],
  templateUrl: './users.component.html',
})
export class UsersComponent implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly auth = inject(AuthService);
  private readonly notify = inject(NotificationService);

  protected readonly users = signal<User[]>([]);
  protected readonly roles = signal<Role[]>([]);
  protected readonly loading = signal(true);
  protected readonly meId = computed(() => this.auth.user()?.id ?? '');

  // Invite form.
  protected readonly showInvite = signal(false);
  protected readonly inviting = signal(false);
  protected invite = this.blankInvite();
  protected readonly tempPassword = signal<{ email: string; password: string | null; link: string | null } | null>(null);

  // Per-user role editing.
  protected readonly editingId = signal<string | null>(null);
  protected editRoles = new Set<string>();
  protected readonly savingRoles = signal(false);

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadUsers(), this.loadRoles()]);
    this.loading.set(false);
  }

  private async loadUsers(): Promise<void> {
    this.users.set(await firstValueFrom(this.admin.users()));
  }

  private async loadRoles(): Promise<void> {
    this.roles.set(await firstValueFrom(this.admin.roles()));
  }

  protected initials(u: User): string {
    return (u.full_name || u.email || u.phone || '')
      .split(' ')
      .map((p) => p[0])
      .slice(0, 2)
      .join('')
      .toUpperCase();
  }

  // ── Invite ──────────────────────────────────────────────────────
  protected toggleInviteRole(code: string): void {
    const set = new Set(this.invite.role_codes);
    set.has(code) ? set.delete(code) : set.add(code);
    this.invite.role_codes = [...set];
  }

  protected async submitInvite(): Promise<void> {
    if (!this.invite.email.trim() || !this.invite.full_name.trim() || this.invite.role_codes.length === 0) return;
    this.inviting.set(true);
    try {
      const created = await firstValueFrom(
        this.admin.createUser({
          email: this.invite.email.trim(),
          full_name: this.invite.full_name.trim(),
          role_codes: this.invite.role_codes,
        }),
      );
      this.tempPassword.set({ email: created.user.email ?? '', password: created.temporary_password ?? null, link: created.invitation_url ?? null });
      this.invite = this.blankInvite();
      this.showInvite.set(false);
      await this.loadUsers();
    } catch {
      /* handled */
    } finally {
      this.inviting.set(false);
    }
  }

  // ── Role editing ────────────────────────────────────────────────
  protected startEdit(u: User): void {
    this.editingId.set(u.id);
    this.editRoles = new Set(u.roles.map((r) => r.code));
  }

  protected cancelEdit(): void {
    this.editingId.set(null);
  }

  protected toggleEditRole(code: string): void {
    this.editRoles.has(code) ? this.editRoles.delete(code) : this.editRoles.add(code);
  }

  protected async toggleActive(u: User): Promise<void> {
    const next = !u.is_active;
    if (!next && !confirm(`Deactivate ${u.full_name}? They'll be signed out and unable to log in.`)) return;
    try {
      const updated = await firstValueFrom(this.admin.setUserActive(u.id, next));
      this.users.update((list) => list.map((x) => (x.id === u.id ? updated : x)));
      this.notify.success(next ? `${u.full_name} reactivated.` : `${u.full_name} deactivated.`);
    } catch {
      /* handled */
    }
  }

  protected async saveRoles(u: User): Promise<void> {
    if (this.editRoles.size === 0) return;
    this.savingRoles.set(true);
    try {
      const updated = await firstValueFrom(this.admin.setUserRoles(u.id, [...this.editRoles]));
      this.users.update((list) => list.map((x) => (x.id === u.id ? updated : x)));
      this.editingId.set(null);
      this.notify.success(`Updated roles for ${u.full_name}.`);
    } catch {
      /* handled */
    } finally {
      this.savingRoles.set(false);
    }
  }

  private blankInvite(): { email: string; full_name: string; role_codes: string[] } {
    return { email: '', full_name: '', role_codes: [] };
  }
}

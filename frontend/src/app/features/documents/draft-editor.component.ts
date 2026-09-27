import { ChangeDetectionStrategy, Component, OnDestroy, inject, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { DraftsService } from '@core/services/drafts.service';
import { NotificationService } from '@core/services/notification.service';
import { TokenService } from '@core/auth/token.service';
import { environment } from '@env/environment';
import {
  DEFAULT_PAGE,
  Draft,
  DraftVersion,
  PageOrientation,
  PageSettings,
  PageSize,
} from '@core/models/drafts.models';
import { EditorChange, VsRichEditorComponent } from '@shared/rich-editor/vs-rich-editor.component';
import { ClientChoice, VsClientPickerComponent } from '@shared/client-picker/vs-client-picker.component';
import { ClientsService } from '@core/services/clients.service';

const AUTOSAVE_MS = 1500;

/**
 * Full-page document editor: title, page setup, autosave, named versions,
 * Word export, filing to the library, print.
 */
@Component({
  selector: 'app-draft-editor',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, MatMenuModule, VsRichEditorComponent, VsClientPickerComponent],
  templateUrl: './draft-editor.component.html',
  styleUrl: './draft-editor.component.scss',
})
export class DraftEditorComponent implements OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly drafts = inject(DraftsService);
  private readonly notify = inject(NotificationService);
  private readonly tokens = inject(TokenService);
  private readonly clients = inject(ClientsService);

  protected readonly editor = viewChild(VsRichEditorComponent);
  protected readonly draft = signal<Draft | null>(null);
  protected readonly loading = signal(true);
  protected readonly saveState = signal<'saved' | 'dirty' | 'saving' | 'error'>('saved');
  protected readonly lastSavedAt = signal<Date | null>(null);
  protected readonly versions = signal<DraftVersion[] | null>(null);
  protected readonly showPageSetup = signal(false);
  protected readonly busy = signal<string | null>(null);
  /** The client this draft is for (null = none); shown and changeable in the title bar. */
  protected readonly client = signal<ClientChoice | null>(null);
  protected readonly showClient = signal(false);
  protected title = '';
  protected page: PageSettings = { ...DEFAULT_PAGE, margins: { ...DEFAULT_PAGE.margins } };
  protected readonly sizes: PageSize[] = ['A4', 'Letter', 'Legal'];
  protected readonly orientations: PageOrientation[] = ['portrait', 'landscape'];

  private pending: EditorChange | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private titleTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((p) => {
      const id = p.get('id');
      if (id) void this.load(id);
    });
    // Leaving the tab mid-edit must not lose the last keystrokes.
    window.addEventListener('beforeunload', this.flushSync);
  }

  ngOnDestroy(): void {
    window.removeEventListener('beforeunload', this.flushSync);
    void this.flush();
  }

  private async load(id: string): Promise<void> {
    this.loading.set(true);
    try {
      const d = await firstValueFrom(this.drafts.get(id));
      this.draft.set(d);
      this.title = d.title;
      this.page = { ...DEFAULT_PAGE, ...d.page, margins: { ...DEFAULT_PAGE.margins, ...(d.page?.margins ?? {}) } };
      this.lastSavedAt.set(new Date(d.updated_at));
      this.client.set(null);
      if (d.client_id) {
        firstValueFrom(this.clients.get(d.client_id))
          .then((c) => this.client.set({ id: c.id, name: c.display_name }))
          .catch(() => this.client.set({ id: d.client_id, name: 'Client' }));
      }
      // The editor renders after `draft` is set; seed it on the next tick.
      setTimeout(() => this.editor()?.setContent(d.content_json ?? d.content_html));
    } catch {
      this.router.navigate(['/app/documents']);
    } finally {
      this.loading.set(false);
    }
  }

  // ── Autosave ───────────────────────────────────────────────────
  protected onChange(change: EditorChange): void {
    this.pending = change;
    this.saveState.set('dirty');
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.flush(), AUTOSAVE_MS);
  }

  /** Pick, add or clear the client; saved straight away. */
  protected async onClient(choice: ClientChoice | null): Promise<void> {
    this.showClient.set(false);
    if (choice && !choice.id) { this.notify.error('Pick a client from the master or add one — a typed name cannot be linked.'); return; }
    this.client.set(choice);
    await this.save({ client_id: choice?.id ?? null });
  }

  protected onTitle(value: string): void {
    this.title = value;
    this.saveState.set('dirty');
    if (this.titleTimer) clearTimeout(this.titleTimer);
    this.titleTimer = setTimeout(() => void this.save({ title: value.trim() || 'Untitled document' }), AUTOSAVE_MS);
  }

  private async flush(): Promise<void> {
    if (!this.pending) return;
    const change = this.pending;
    this.pending = null;
    await this.save({ content_json: change.json, content_html: change.html });
  }

  private readonly flushSync = (): void => {
    const d = this.draft();
    if (!this.pending || !d) return;
    // keepalive lets the request outlive the page. The access token lives in
    // memory (TokenService), never in storage.
    const token = this.tokens.accessToken() ?? '';
    void fetch(`${environment.apiBaseUrl}/drafts/${d.id}`, {
      method: 'PATCH', keepalive: true,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ content_json: this.pending.json, content_html: this.pending.html }),
    });
  };

  private async save(payload: Parameters<DraftsService['update']>[1]): Promise<void> {
    const d = this.draft();
    if (!d) return;
    this.saveState.set('saving');
    for (let attempt = 0; ; attempt++) {
      try {
        const updated = await firstValueFrom(this.drafts.update(d.id, payload));
        this.draft.set({ ...updated, content_json: d.content_json, content_html: d.content_html });
        this.lastSavedAt.set(new Date(updated.updated_at));
        this.saveState.set(this.pending ? 'dirty' : 'saved');
        return;
      } catch (err) {
        // A network-level failure (status 0 — e.g. a request caught in the
        // service worker's first activation) is worth one quiet retry; the
        // PATCH is idempotent.
        const status = err instanceof HttpErrorResponse ? err.status : 0;
        if (status === 0 && attempt === 0) {
          await new Promise((r) => setTimeout(r, 1000));
          continue;
        }
        this.saveState.set('error');
        return;
      }
    }
  }

  // ── Page setup ─────────────────────────────────────────────────
  protected async applyPage(): Promise<void> {
    this.page = { ...this.page, margins: { ...this.page.margins } };
    this.showPageSetup.set(false);
    await this.save({ page: this.page });
  }

  // ── Versions ───────────────────────────────────────────────────
  protected async toggleVersions(): Promise<void> {
    if (this.versions() !== null) { this.versions.set(null); return; }
    const d = this.draft();
    if (!d) return;
    this.versions.set(await firstValueFrom(this.drafts.versions(d.id)));
  }

  protected async saveVersion(): Promise<void> {
    const d = this.draft();
    if (!d) return;
    const note = window.prompt('Name this version (optional)', '') ?? null;
    if (note === null) return;
    await this.flush();
    try {
      await firstValueFrom(this.drafts.saveVersion(d.id, note.trim() || null));
      this.notify.success('Version saved.');
      if (this.versions() !== null) this.versions.set(await firstValueFrom(this.drafts.versions(d.id)));
    } catch { /* handled */ }
  }

  protected async restore(v: DraftVersion): Promise<void> {
    const d = this.draft();
    if (!d || !window.confirm(`Restore version ${v.version_no}? The current text is saved as a version first.`)) return;
    try {
      const restored = await firstValueFrom(this.drafts.restore(d.id, v.id));
      this.draft.set(restored);
      this.editor()?.setContent(restored.content_json);
      this.versions.set(await firstValueFrom(this.drafts.versions(d.id)));
      this.notify.success(`Version ${v.version_no} restored.`);
    } catch { /* handled */ }
  }

  // ── Export / file / print ──────────────────────────────────────
  protected async exportDocx(): Promise<void> {
    const d = this.draft();
    if (!d) return;
    this.busy.set('docx');
    try {
      await this.flush();
      const blob = await firstValueFrom(this.drafts.exportDocx(d.id));
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${this.title.trim() || 'Document'}.docx`; a.click();
      URL.revokeObjectURL(url);
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  protected async fileToLibrary(): Promise<void> {
    const d = this.draft();
    if (!d) return;
    this.busy.set('file');
    try {
      await this.flush();
      const doc = await firstValueFrom(this.drafts.fileToLibrary(d.id, null));
      this.draft.update((cur) => (cur ? { ...cur, library_document_id: doc.id } : cur));
      this.notify.success(`${doc.name} — version ${doc.version_count} in My documents.`);
    } catch { /* handled */ } finally { this.busy.set(null); }
  }

  protected print(): void {
    const p = this.page;
    const style = document.createElement('style');
    style.id = 'vs-print-page';
    style.textContent = `@page { size: ${p.size} ${p.orientation}; margin: ${p.margins.top}mm ${p.margins.right}mm ${p.margins.bottom}mm ${p.margins.left}mm; }`;
    document.head.appendChild(style);
    window.print();
    setTimeout(() => style.remove(), 1000);
  }

  protected async remove(): Promise<void> {
    const d = this.draft();
    if (!d || !window.confirm(`Delete "${d.title}"? This cannot be undone.`)) return;
    try {
      await firstValueFrom(this.drafts.remove(d.id));
      this.pending = null;
      this.router.navigate(['/app/documents'], { queryParams: { view: 'drafts' } });
    } catch { /* handled */ }
  }
}

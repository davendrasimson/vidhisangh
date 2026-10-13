import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { firstValueFrom } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '@core/auth/auth.service';
import { KnowledgeService } from '@core/services/knowledge.service';
import { DocumentsService } from '@core/services/documents.service';
import { MattersService } from '@core/services/matters.service';
import { NotificationService } from '@core/services/notification.service';
import { KnowledgeCategory, KnowledgeItem, KnowledgeSummary } from '@core/models/knowledge.models';
import { DocFile } from '@core/models/documents.models';
import { Matter } from '@core/models/matters.models';
import { ActsLibraryComponent } from './acts-library.component';
import { KnowledgeBookmarks } from './knowledge-bookmarks.service';
import { ACTS } from './data/acts';
import { FIRM_LIBRARY_STARTERS, filteredFirmStarters } from './data/firm-library-starters';
import { checklistLines, fillTemplate, placeholders } from './knowledge.helpers';
import { VsDateInputComponent } from '@shared/date-input/vs-date-input.component';

import { saveBlob } from '@core/platform/save-file';
@Component({
  selector: 'app-knowledge', standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [VsDateInputComponent, FormsModule, DatePipe, RouterLink, MatIconModule, MatButtonModule, ActsLibraryComponent],
  templateUrl: './knowledge.component.html',
})
export class KnowledgeComponent implements OnInit {
  protected readonly auth = inject(AuthService);
  protected readonly bookmarks = inject(KnowledgeBookmarks);
  private readonly kb = inject(KnowledgeService);
  private readonly documents = inject(DocumentsService);
  private readonly matters = inject(MattersService);
  private readonly notify = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private listRequest = 0;
  private detailRequest = 0;

  protected readonly actCount = ACTS.length;
  protected readonly view = signal<'acts' | 'firm'>('acts');
  protected readonly items = signal<KnowledgeSummary[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal(false);
  protected readonly syncError = signal(false);
  protected readonly category = signal<KnowledgeCategory | ''>('');
  protected readonly savedOnly = signal(false);
  protected search = '';
  protected practiceArea = '';
  protected readonly visible = computed(() => this.items().filter((i) => !this.savedOnly() || this.bookmarks.has(`item:${i.id}`)));
  protected readonly selected = signal<KnowledgeItem | null>(null);
  protected readonly detailLoading = signal(false);
  protected readonly attachments = signal<DocFile[]>([]);
  protected readonly attachmentError = signal(false);
  protected readonly showAdd = signal(false);
  protected readonly editingId = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly copyingStarter = signal(false);
  protected readonly uploading = signal(false);
  protected readonly formAttachments = signal<DocFile[]>([]);
  private retainedAttachmentIds: string[] = [];
  protected addForm = this.blank();
  protected readonly deleteConfirm = signal(false);
  protected readonly deleting = signal(false);
  protected readonly today = new Date().toLocaleDateString('en-CA');
  protected readonly starterCount = FIRM_LIBRARY_STARTERS.length;

  protected readonly showUse = signal(false);
  protected readonly matterList = signal<Matter[]>([]);
  protected readonly matterLoading = signal(false);
  protected readonly matterError = signal(false);
  protected readonly applying = signal(false);
  protected readonly appliedTasks = signal(0);
  protected readonly appliedMatterId = signal<string | null>(null);
  protected useMatterId = '';
  protected draftTitle = '';
  protected readonly draftBody = signal('');
  protected readonly values = signal<Record<string, string>>({});
  protected readonly fields = computed(() => placeholders(this.draftBody()));
  protected readonly filledBody = computed(() => fillTemplate(this.draftBody(), this.values()));
  protected readonly taskLines = computed(() => checklistLines(this.filledBody()));
  protected readonly unresolvedFields = computed(() => placeholders(this.filledBody()));

  protected readonly categories: { value: KnowledgeCategory | ''; label: string }[] = [
    { value: '', label: 'All resources' }, { value: 'template', label: 'Templates' },
    { value: 'precedent', label: 'Precedents' }, { value: 'sop', label: 'Practice guides' },
    { value: 'checklist', label: 'Checklists' }, { value: 'note', label: 'Notes' },
  ];

  constructor() {
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      this.view.set(params.get('view') === 'firm' ? 'firm' : 'acts');
    });
  }

  async ngOnInit(): Promise<void> { await this.load(); }

  protected switchView(view: 'acts' | 'firm'): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { view, act: null }, queryParamsHandling: 'merge' });
  }

  protected async setCategory(category: KnowledgeCategory | ''): Promise<void> {
    this.category.set(category); await this.load();
  }

  protected async load(): Promise<void> {
    const request = ++this.listRequest;
    const filters = { category: this.category(), q: this.search.trim(), practice_area: this.practiceArea.trim() };
    const starters = filteredFirmStarters(filters.category, filters.q, filters.practice_area);
    this.loading.set(true); this.error.set(false); this.syncError.set(false);
    try {
      const all: KnowledgeSummary[] = [];
      for (let page = 1; ; page++) {
        const batch = await firstValueFrom(this.kb.list({ ...filters, page, size: 50 }));
        if (request !== this.listRequest) return;
        all.push(...batch);
        if (batch.length < 50) break;
      }
      this.items.set([...all, ...starters]);
    } catch {
      if (request === this.listRequest) {
        this.items.set(starters);
        this.syncError.set(true);
      }
    }
    finally { if (request === this.listRequest) this.loading.set(false); }
  }

  protected async openItem(item: KnowledgeSummary): Promise<void> {
    const request = ++this.detailRequest;
    this.selected.set(null); this.detailLoading.set(true); this.showAdd.set(false);
    this.showUse.set(false); this.appliedMatterId.set(null); this.deleteConfirm.set(false); this.attachments.set([]); this.attachmentError.set(false);
    const starterItem = FIRM_LIBRARY_STARTERS.find((resource) => resource.id === item.id);
    if (starterItem) {
      this.selected.set(starterItem);
      this.detailLoading.set(false);
      return;
    }
    try {
      const full = await firstValueFrom(this.kb.get(item.id));
      if (request !== this.detailRequest) return;
      this.selected.set(full);
      const results = await Promise.allSettled((full.attachments ?? []).map((id) => firstValueFrom(this.documents.get(id))));
      if (request !== this.detailRequest) return;
      this.attachments.set(results.flatMap((r) => r.status === 'fulfilled' ? [r.value] : []));
      this.attachmentError.set(results.some((r) => r.status === 'rejected'));
    } catch { if (request === this.detailRequest) this.notify.error('Could not open this resource. Please try again.'); }
    finally { if (request === this.detailRequest) this.detailLoading.set(false); }
  }

  protected back(): void {
    ++this.detailRequest; this.selected.set(null); this.detailLoading.set(false);
    this.showUse.set(false); this.deleteConfirm.set(false);
  }

  protected newItem(): void {
    this.back(); this.editingId.set(null); this.addForm = this.blank();
    this.formAttachments.set([]); this.retainedAttachmentIds = []; this.showAdd.set(true);
    this.switchView('firm');
  }

  protected edit(): void {
    const item = this.selected(); if (!item) return;
    if (this.isStarter(item)) return;
    this.editingId.set(item.id);
    this.addForm = { title: item.title, category: item.category, body: item.body, practice_area: item.practice_area ?? '',
      tags: item.tags.join(', '), source_url: item.source_url ?? '', reviewed_on: item.reviewed_on ?? '' };
    this.formAttachments.set(this.attachments());
    this.retainedAttachmentIds = (item.attachments ?? []).filter((id) => !this.attachments().some((a) => a.id === id));
    this.showAdd.set(true); this.showUse.set(false);
  }

  protected starter(kind: 'template' | 'checklist' | 'note'): void {
    this.newItem(); this.addForm.category = kind;
    this.addForm.title = kind === 'template' ? 'Client matter brief' : kind === 'checklist' ? 'Matter preparation checklist' : 'Research note';
    this.addForm.body = kind === 'template'
      ? 'Client: {{client_name}}\nMatter: {{matter_title}}\nReference: {{matter_number}}\n\nBackground\n{{background}}\n\nQuestions to resolve\n{{questions}}\n\nDocuments available\n{{documents}}\n\nNext steps for review\n{{next_steps}}'
      : kind === 'checklist' ? '- Confirm client details and instructions\n- Collect relevant documents\n- Prepare a chronology\n- Identify applicable law and forum\n- Check limitation and other deadlines\n- Review the draft with the responsible lawyer'
      : 'Question\n\nRelevant facts\n\nApplicable Act and provisions\n\nAuthorities and source links\n\nAnalysis\n\nOpen questions\n\nConclusion for review';
  }

  protected async uploadAttachment(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0]; if (!file) return;
    if (this.formAttachments().length + this.retainedAttachmentIds.length >= 20) { this.notify.error('Use up to 20 attachments.'); input.value = ''; return; }
    if (file.size > 20 * 1024 * 1024) { this.notify.error('Choose a file smaller than 20 MB.'); input.value = ''; return; }
    this.uploading.set(true);
    try {
      const uploaded = await firstValueFrom(this.documents.upload(file));
      this.formAttachments.update((items) => [...items, uploaded]);
    } catch { this.notify.error('Upload failed. Your other changes are still here.'); }
    finally { this.uploading.set(false); input.value = ''; }
  }

  protected detach(id: string): void { this.formAttachments.update((items) => items.filter((a) => a.id !== id)); }

  protected async download(file: DocFile): Promise<void> {
    try {
      const blob = await firstValueFrom(this.documents.download(file.id));
      await saveBlob(blob, file.name);
    } catch { this.notify.error('Could not download the attachment.'); }
  }

  protected async submitAdd(): Promise<void> {
    const f = this.addForm;
    if (f.title.trim().length < 2 || !f.body.trim() || this.saving() || this.uploading()) return;
    if (f.source_url && !/^https?:\/\//i.test(f.source_url.trim())) { this.notify.error('Use a full http or https source URL.'); return; }
    const tags = [...new Set(f.tags.split(',').map((s) => s.trim()).filter(Boolean))];
    if (tags.length > 20) { this.notify.error('Use up to 20 tags.'); return; }
    this.saving.set(true);
    try {
      const payload = { title: f.title.trim(), category: f.category, body: f.body, practice_area: f.practice_area.trim() || null,
        tags, source_url: f.source_url.trim() || null, reviewed_on: f.reviewed_on || null,
        attachments: [...this.retainedAttachmentIds, ...this.formAttachments().map((a) => a.id)] };
      const id = this.editingId();
      const saved = await firstValueFrom(id ? this.kb.update(id, payload) : this.kb.create(payload));
      this.showAdd.set(false); this.selected.set(saved); this.attachments.set(this.formAttachments());
      this.attachmentError.set(this.retainedAttachmentIds.length > 0);
      this.notify.success(id ? 'Resource updated.' : 'Resource added to the firm library.');
      await this.load();
    } catch { /* interceptor explains API validation and permissions */ }
    finally { this.saving.set(false); }
  }

  protected async remove(): Promise<void> {
    const item = this.selected(); if (!item || this.deleting()) return;
    if (this.isStarter(item)) return;
    this.deleting.set(true);
    try { await firstValueFrom(this.kb.remove(item.id)); this.back(); await this.load(); this.notify.success('Resource deleted.'); }
    catch { /* interceptor */ } finally { this.deleting.set(false); }
  }

  protected async beginUse(): Promise<void> {
    const item = this.selected(); if (!item) return;
    this.showUse.set(true); this.appliedTasks.set(0); this.appliedMatterId.set(null);
    this.useMatterId = ''; this.draftTitle = item.title; this.draftBody.set(item.body); this.values.set({});
    await this.loadMatters();
  }

  protected isStarter(item: KnowledgeSummary): boolean { return item.id.startsWith('starter-'); }

  protected resourceSummary(item: KnowledgeSummary): string {
    const starterItem = FIRM_LIBRARY_STARTERS.find((resource) => resource.id === item.id);
    if (!starterItem) return item.practice_area || 'Firm knowledge resource';
    const paragraph = starterItem.body.split(/\n\s*\n/).find((part) => part.trim().split(/\s+/).length > 8) ?? starterItem.body;
    const summary = paragraph.replace(/\{\{[^}]+\}\}/g, 'matter details').replace(/\s+/g, ' ').trim();
    return summary.length > 150 ? `${summary.slice(0, 147)}…` : summary;
  }

  protected categoryCount(value: KnowledgeCategory | ''): number {
    return value ? FIRM_LIBRARY_STARTERS.filter((item) => item.category === value).length : FIRM_LIBRARY_STARTERS.length;
  }

  protected async copyStarterToFirm(): Promise<void> {
    const item = this.selected();
    if (!item || !this.isStarter(item) || this.copyingStarter()) return;
    this.copyingStarter.set(true);
    try {
      const saved = await firstValueFrom(this.kb.create({
        title: item.title,
        category: item.category,
        body: item.body,
        practice_area: item.practice_area,
        tags: item.tags.filter((tag) => tag !== 'India'),
        source_url: item.source_url,
        reviewed_on: null,
        attachments: [],
      }));
      this.selected.set(saved);
      this.notify.success('Editable copy added to your firm library.');
      await this.load();
    } catch { /* interceptor explains validation and permissions */ }
    finally { this.copyingStarter.set(false); }
  }

  protected async loadMatters(): Promise<void> {
    this.matterLoading.set(true); this.matterError.set(false);
    try {
      const all: Matter[] = [];
      for (let page = 1; ; page++) {
        const batch = await firstValueFrom(this.matters.list(undefined, page, 50));
        all.push(...batch); if (batch.length < 50) break;
      }
      this.matterList.set(all.filter((m) => m.status !== 'closed'));
    } catch { this.matterError.set(true); }
    finally { this.matterLoading.set(false); }
  }

  protected chooseMatter(id: string): void {
    this.useMatterId = id;
    const matter = this.matterList().find((m) => m.id === id);
    if (matter) this.values.update((v) => ({ ...v, client_name: matter.client_name, matter_title: matter.title, matter_number: matter.matter_number }));
  }

  protected setValue(key: string, value: string): void { this.values.update((v) => ({ ...v, [key]: value })); }

  protected async applyToMatter(): Promise<void> {
    const item = this.selected();
    if (!item || !this.useMatterId || this.applying() || this.unresolvedFields().length || !this.filledBody().trim()) return;
    const isChecklist = item.category === 'checklist';
    if (isChecklist && (!this.taskLines().length || this.taskLines().length > 50 || this.taskLines().some((t) => t.length > 300))) {
      this.notify.error('Use 1–50 checklist lines, each no longer than 300 characters.'); return;
    }
    if (!isChecklist && !this.draftTitle.trim()) return;
    this.applying.set(true);
    try {
      if (isChecklist) {
        for (let index = this.appliedTasks(); index < this.taskLines().length; index++) {
          await firstValueFrom(this.matters.addTask(this.useMatterId, this.taskLines()[index]));
          this.appliedTasks.set(index + 1);
        }
      } else {
        const file = new File([this.filledBody()], `${this.draftTitle.trim().replace(/[\\/]/g, '-')}.txt`, { type: 'text/plain' });
        await firstValueFrom(this.documents.upload(file, this.draftTitle.trim(), null, this.useMatterId));
      }
      this.appliedMatterId.set(this.useMatterId); this.showUse.set(false);
      this.notify.success(isChecklist ? 'Checklist added as matter tasks.' : 'Draft saved to the matter’s documents.');
    } catch { this.notify.error(isChecklist ? `${this.appliedTasks()} tasks added. Retry continues after the confirmed tasks; check the matter if the connection was interrupted.` : 'Could not confirm the draft was saved. Check the matter before retrying.'); }
    finally { this.applying.set(false); }
  }

  private blank() { return { title: '', category: 'template' as KnowledgeCategory, body: '', practice_area: '', tags: '', source_url: '', reviewed_on: '' }; }
}

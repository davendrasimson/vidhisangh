import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { DraftsService } from '@core/services/drafts.service';
import { DraftTemplate as FirmDraftTemplate, DraftTemplateField, DraftTemplateSummary, DraftSummary, EditorDoc } from '@core/models/drafts.models';
import { EditorChange, VsRichEditorComponent } from '@shared/rich-editor/vs-rich-editor.component';
import { draftTextToHtml } from './draft-html';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { AuthService } from '@core/auth/auth.service';
import { DocFile, DocFolder, DocVersion, SignatureEnvelope, SignatureSignerInput, SignatureStep } from '@core/models/documents.models';
import { DocumentsService } from '@core/services/documents.service';
import { NotificationService } from '@core/services/notification.service';
import { DRAFT_TEMPLATES, DraftCategory, DraftLanguage, DraftRole, DraftTemplate, FIELD_LABELS, LocalText, renderDraft } from './legal-drafting-templates';
import { ORDER_LONG_FIELDS, ORDER_STATES, OrderState, orderStateFor, withOrderDefaults } from './judicial-orders';
import { ClientChoice, VsClientPickerComponent } from '@shared/client-picker/vs-client-picker.component';
import { ProfileService } from '@core/services/profile.service';
import { ProfileDetail } from '@core/models/profile.models';
import { MattersService } from '@core/services/matters.service';
import { ECourtsCase, MatterDetail, Person } from '@core/models/matters.models';
import { SignaturePadComponent } from '@shared/signature-pad/signature-pad.component';

import { saveBlob } from '@core/platform/save-file';
import { isNativeApp } from '@core/platform/platform';
const todayDdMmYyyy = (): string => { const d = new Date(); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`; };

@Component({
  selector: 'app-documents',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DatePipe, MatIconModule, MatButtonModule, MatMenuModule, VsRichEditorComponent, VsClientPickerComponent, SignaturePadComponent],
  templateUrl: './documents.component.html',
  styleUrl: './documents.component.scss',
})
export class DocumentsComponent implements OnInit {
  private readonly docs = inject(DocumentsService);
  private readonly notify = inject(NotificationService);
  private readonly auth = inject(AuthService);
  private readonly drafts = inject(DraftsService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly editor = viewChild(VsRichEditorComponent);
  private readonly profiles = inject(ProfileService);
  private readonly matters = inject(MattersService);

  protected readonly view = signal<'draft' | 'drafts' | 'files' | 'signatures'>('draft');
  /** Who this work is for. Null = no client (office formats, the firm's own papers).
   *  New drafts and uploads carry it; lists narrow to it while `onlyClient` is on. */
  protected readonly client = signal<ClientChoice | null>(null);
  /** Matter context supplied by the matter command centre. */
  protected readonly matterId = signal<string | null>(null);
  protected readonly matterTitle = signal<string | null>(null);
  protected readonly onlyClient = signal(true);
  protected readonly showClientPicker = signal(false);
  /** The generated draft as editor HTML; the editor's own state after edits. */
  protected readonly draftHtml = signal<string | EditorDoc>('');
  private editorChange: EditorChange | null = null;
  protected readonly myDrafts = signal<DraftSummary[]>([]);
  protected readonly draftsLoading = signal(false);
  protected readonly language = signal<DraftLanguage>('en');
  protected readonly role = signal<DraftRole>('all');
  protected readonly category = signal<DraftCategory>('all');
  protected readonly profile = signal<ProfileDetail | null>(null);
  protected readonly ecourtsLoading = signal(false);
  protected readonly ecourtsCase = signal<ECourtsCase | null>(null);
  protected cnrNumber = '';
  protected readonly isJudicialUser = computed(() =>
    ['judicial_officer', 'retired_judicial_officer'].includes(this.profile()?.professional_role ?? ''),
  );
  /** Sitting judicial officer (token claim): no clients, no firm, only the court's formats. */
  protected readonly judge = this.auth.isJudicial;
  /** Whose High Court practice the order heading follows (from the profile's state, changeable). */
  protected readonly orderState = signal<OrderState>('general');
  protected readonly orderStates = ORDER_STATES;
  /** A judge sees only the categories that hold judicial formats. */
  private readonly judicialCategories = new Set(DRAFT_TEMPLATES.filter((item) => item.roles.includes('judicial')).map((item) => item.category));
  protected showCategory(id: DraftCategory): boolean {
    if (this.judge()) return id === 'all' || this.judicialCategories.has(id as Exclude<DraftCategory, 'all'>);
    return id !== 'judicial' || this.isJudicialUser();
  }
  protected readonly templateSearch = signal('');
  protected readonly templates = DRAFT_TEMPLATES;
  protected readonly selectedTemplate = signal<DraftTemplate>(DRAFT_TEMPLATES[0]);
  protected readonly selectedWordTemplate = signal<FirmDraftTemplate | null>(null);
  protected readonly wordTemplates = signal<DraftTemplateSummary[]>([]);
  protected readonly templatesLoading = signal(false);
  protected readonly uploadingTemplate = signal(false);
  protected readonly showTemplateManager = signal(false);
  protected editingTemplate: FirmDraftTemplate | null = null;
  protected readonly draftValues = signal<Record<string, string>>({ date: todayDdMmYyyy() });
  protected readonly draftText = signal('');
  protected readonly savingDraft = signal(false);
  protected draftFileName = 'Civil plaint';

  protected readonly languages: { id: DraftLanguage; short: string; name: string; sample: string }[] = [
    { id: 'en', short: 'EN', name: 'English', sample: 'Court drafting' },
    { id: 'hi', short: 'हि', name: 'हिन्दी', sample: 'न्यायालय मसौदा' },
    { id: 'pa', short: 'ਪੰ', name: 'ਪੰਜਾਬੀ', sample: 'ਅਦਾਲਤੀ ਖਰੜਾ' },
  ];
  protected readonly roles: { id: DraftRole; label: LocalText }[] = [
    { id: 'all', label: { en: 'All roles', hi: 'सभी भूमिकाएँ', pa: 'ਸਾਰੀਆਂ ਭੂਮਿਕਾਵਾਂ' } },
    { id: 'advocate', label: { en: 'Advocate / counsel', hi: 'अधिवक्ता / काउंसल', pa: 'ਵਕੀਲ / ਕੌਂਸਲ' } },
    { id: 'associate', label: { en: 'Junior / associate', hi: 'जूनियर / सहयोगी', pa: 'ਜੂਨੀਅਰ / ਸਹਿਯੋਗੀ' } },
    { id: 'clerk', label: { en: 'Clerk / Munshi', hi: 'क्लर्क / मुंशी', pa: 'ਕਲਰਕ / ਮੁਨਸ਼ੀ' } },
    { id: 'judicial', label: { en: 'Judicial officer', hi: 'न्यायिक अधिकारी', pa: 'ਨਿਆਂਇਕ ਅਧਿਕਾਰੀ' } },
  ];
  protected readonly categories: { id: DraftCategory; label: LocalText }[] = [
    { id: 'all', label: { en: 'All', hi: 'सभी', pa: 'ਸਾਰੇ' } },
    { id: 'civil', label: { en: 'Civil', hi: 'दीवानी', pa: 'ਦੀਵਾਨੀ' } },
    { id: 'criminal', label: { en: 'Criminal', hi: 'आपराधिक', pa: 'ਫੌਜਦਾਰੀ' } },
    { id: 'family', label: { en: 'Family', hi: 'पारिवारिक', pa: 'ਪਰਿਵਾਰਕ' } },
    { id: 'property', label: { en: 'Property', hi: 'संपत्ति', pa: 'ਜਾਇਦਾਦ' } },
    { id: 'commercial', label: { en: 'Commercial', hi: 'वाणिज्यिक', pa: 'ਵਪਾਰਕ' } },
    { id: 'office', label: { en: 'Court office', hi: 'अदालती कार्यालय', pa: 'ਅਦਾਲਤੀ ਦਫ਼ਤਰ' } },
    { id: 'judicial', label: { en: 'Judicial orders', hi: 'न्यायिक आदेश', pa: 'ਨਿਆਂਇਕ ਹੁਕਮ' } },
  ];
  protected readonly filteredTemplates = computed(() => {
    const query = this.templateSearch().trim().toLowerCase();
    return this.templates.filter((item) => {
      if (item.roles.includes('judicial') && !this.isJudicialUser()) return false;
      const categoryMatch = this.category() === 'all' || item.category === this.category();
      const roleMatch = this.role() === 'all' || item.roles.includes(this.role() as Exclude<DraftRole, 'all'>);
      const text = `${item.title.en} ${item.title.hi} ${item.title.pa} ${item.description.en} ${item.tags.join(' ')}`.toLowerCase();
      return categoryMatch && roleMatch && (!query || text.includes(query));
    });
  });

  protected readonly folder = signal<DocFolder | null>(null);
  protected readonly subfolders = signal<DocFolder[]>([]);
  protected readonly files = signal<DocFile[]>([]);
  protected readonly loading = signal(true);
  protected readonly search = signal('');
  protected readonly showFolderInput = signal(false);
  protected folderName = '';
  protected readonly openVersions = signal<Record<string, DocVersion[] | undefined>>({});
  private versioning: DocFile | null = null;
  protected readonly myId = computed(() => this.auth.user()?.id ?? '');
  protected readonly signatureEnvelopes = signal<SignatureEnvelope[]>([]);
  protected readonly teamPeople = signal<Person[]>([]);
  protected readonly signingLoading = signal(false);
  protected readonly preparingDocument = signal<DocFile | null>(null);
  protected signatureTitle = '';
  protected signatureMessage = 'Please review and electronically sign this document.';
  protected sequentialSigning = true;
  protected signerRows: SignatureSignerInput[] = [];
  protected readonly signingStep = signal<SignatureStep | null>(null);
  protected signingName = '';
  protected signingDesignation = '';
  protected signingRemarks = '';
  protected signingConsent = false;
  protected readonly signingImage = signal('');

  async ngOnInit(): Promise<void> {
    // Arriving from a client record: /app/documents?client_id=…&client_name=…
    const q = this.route.snapshot.queryParamMap;
    if (q.get('client_id') && q.get('client_name')) this.client.set({ id: q.get('client_id'), name: q.get('client_name')! });
    this.matterId.set(q.get('matter_id'));
    this.matterTitle.set(q.get('matter_title'));
    this.draftValues.set({
      date: todayDdMmYyyy(),
      clientName: q.get('client_name') || '', client_name: q.get('client_name') || '',
      matterTitle: q.get('matter_title') || '', matter_title: q.get('matter_title') || '',
      caseTitle: q.get('matter_title') || '', case_title: q.get('matter_title') || '',
    });
    this.refreshDraft();
    await Promise.all([this.loadWordTemplates(), this.loadProfile()]);
    if (this.isJudicialUser()) {
      this.orderState.set(orderStateFor(this.profile()?.judicial_state));
      this.role.set('judicial');
      this.category.set(this.judge() ? 'all' : 'judicial');
      this.chooseTemplate(this.templates.find((item) => item.kind === 'order') ?? this.templates[0]);
      if (this.matterId()) await this.loadMatterForOrder(this.matterId()!);
    }
    if (q.get('manage_templates') === '1') this.showTemplateManager.set(true);
    // Deep link from the editor's back button: /app/documents?view=drafts
    if (this.route.snapshot.queryParamMap.get('view') === 'drafts') await this.showDrafts();
    await this.load();
    if (q.get('view') === 'signatures') await this.showSignatures();
  }

  /** Picked, added or cleared the client — the lists follow it. */
  protected async setClient(choice: ClientChoice | null): Promise<void> {
    this.client.set(choice);
    this.showClientPicker.set(false);
    await this.reloadLists();
  }
  protected openClient(id: string): void { void this.router.navigate(['/app/clients', id]); }
  protected async toggleOnlyClient(): Promise<void> { this.onlyClient.update((v) => !v); await this.reloadLists(); }
  private async reloadLists(): Promise<void> {
    await this.load();
    if (this.view() === 'drafts') await this.showDrafts();
  }
  /** The client id the lists should be narrowed to, if any. */
  private listClientId(): string | undefined {
    const c = this.client();
    return this.onlyClient() && c?.id ? c.id : undefined;
  }
  protected local(value: LocalText): string { return value[this.language()]; }
  protected fieldLabel(key: string): string {
    const custom = this.selectedWordTemplate()?.fields.find((field) => field.key === key);
    return custom?.label ?? FIELD_LABELS[key]?.[this.language()] ?? key;
  }
  protected isLongField(key: string): boolean {
    const custom = this.selectedWordTemplate()?.fields.find((field) => field.key === key);
    return custom?.type === 'multiline' || ORDER_LONG_FIELDS.has(key) || ['facts', 'grounds', 'relief', 'terms', 'propertyDetails', 'powers', 'marriageDetails', 'orderBody', 'appearances'].includes(key);
  }
  protected activeFields(): string[] { return this.selectedWordTemplate()?.fields.map((field) => field.key) ?? this.selectedTemplate().fields; }
  protected activeTitle(): string { return this.selectedWordTemplate()?.name ?? this.local(this.selectedTemplate().title); }
  protected activeDescription(): string { return this.selectedWordTemplate()?.description || (this.selectedWordTemplate() ? 'Uploaded Word template' : this.local(this.selectedTemplate().description)); }
  protected setLanguage(language: DraftLanguage): void {
    this.language.set(language);
    this.draftFileName = this.selectedWordTemplate()?.name ?? this.local(this.selectedTemplate().title);
    if (!this.selectedWordTemplate()) this.draftValues.update((values) => withOrderDefaults(this.selectedTemplate(), language, values, this.orderState()));
    this.refreshDraft();
  }
  protected setOrderState(state: OrderState): void {
    this.orderState.set(state);
    this.draftValues.update((values) => withOrderDefaults(this.selectedTemplate(), this.language(), values, state));
    this.refreshDraft();
  }
  protected chooseTemplate(template: DraftTemplate): void {
    this.selectedWordTemplate.set(null);
    this.selectedTemplate.set(template);
    this.draftValues.set(this.startingValues(template));
    this.draftFileName = this.local(template.title);
    this.refreshDraft();
    setTimeout(() => document.querySelector('.draft-builder')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }
  protected async chooseWordTemplate(template: DraftTemplateSummary): Promise<void> {
    try {
      const detail = await firstValueFrom(this.drafts.template(template.id));
      this.selectedWordTemplate.set(detail);
      this.draftValues.set({ ...this.judicialDefaults(), client_name: this.client()?.name ?? '', matter_title: this.matterTitle() ?? '' });
      this.draftFileName = detail.name;
      this.refreshDraft();
      setTimeout(() => document.querySelector('.draft-builder')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    } catch { /* handled */ }
  }
  protected updateField(key: string, value: string): void { this.draftValues.update((current) => ({ ...current, [key]: value })); this.refreshDraft(); }
  protected updateDraftText(value: string): void { this.draftText.set(value); }
  protected resetDraft(): void { this.draftValues.set(this.startingValues(this.selectedTemplate())); this.ecourtsCase.set(null); this.refreshDraft(); }
  private startingValues(template: DraftTemplate): Record<string, string> {
    if (template.kind !== 'order') return { date: todayDdMmYyyy() };
    return withOrderDefaults(template, this.language(), this.judicialDefaults(), this.orderState());
  }
  protected async copyDraft(): Promise<void> {
    try { await navigator.clipboard.writeText(this.draftText()); this.notify.success('Draft copied to clipboard.'); }
    catch { this.notify.error('Could not copy the draft.'); }
  }
  protected downloadDraft(): void { this.save(new Blob(['\ufeff', this.draftText()], { type: 'text/plain;charset=utf-8' }), this.cleanFilename(this.draftFileName) + '.txt'); }
  protected printDraft(): void {
    const escaped = this.draftText().replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>${this.cleanFilename(this.draftFileName)}</title><style>body{font:15px/1.65 Georgia,serif;max-width:760px;margin:48px auto;padding:0 28px;color:#111}pre{font:inherit;white-space:pre-wrap}@media print{body{margin:0 auto}}</style></head><body><pre>${escaped}</pre><script>print()<\/script></body></html>`;
    const page = new Blob([html], { type: 'text/html;charset=utf-8' });
    // No print dialog inside the app: hand the page to the share sheet instead
    // ("Print" is one of its targets on both Android and iOS).
    if (isNativeApp()) { void saveBlob(page, `${this.cleanFilename(this.draftFileName)}.html`); return; }
    const url = URL.createObjectURL(page);
    window.open(url, '_blank', 'noopener,noreferrer');
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }
  /** Keep the draft (autosaved from here on) and file a Word copy into My documents. */
  protected async saveDraftToDocuments(): Promise<void> {
    if (!this.draftText().trim()) return;
    this.savingDraft.set(true);
    try {
      const created = await this.createDraftFromBuilder();
      const filed = await firstValueFrom(this.drafts.fileToLibrary(created.id, this.folder()?.id ?? null));
      this.files.update((items) => [filed, ...items.filter((f) => f.id !== filed.id)]);
      this.notify.success(`${filed.name} saved to My documents (and kept in My drafts).`);
    } catch { /* handled by interceptor */ } finally { this.savingDraft.set(false); }
  }
  protected async downloadWordFromBuilder(): Promise<void> {
    if (!this.draftText().trim() || this.savingDraft()) return;
    this.savingDraft.set(true);
    try {
      const created = await this.createDraftFromBuilder();
      const blob = await firstValueFrom(this.drafts.exportDocx(created.id));
      this.save(blob, `${this.cleanFilename(this.draftFileName)}.docx`);
      this.notify.success('Word document prepared for signing and execution.');
    } catch { /* handled */ }
    finally { this.savingDraft.set(false); }
  }
  private refreshDraft(): void {
    const custom = this.selectedWordTemplate();
    if (custom) {
      const content = this.fillWordTemplate(custom.content_json, custom.fields, this.draftValues());
      this.draftHtml.set(content);
      this.draftText.set(this.editorText(content));
      this.editorChange = null;
      this.editor()?.setContent(content);
      return;
    }
    const text = renderDraft(this.selectedTemplate(), this.language(), this.draftValues(), this.orderState());
    this.draftText.set(text);
    const html = draftTextToHtml(text);
    this.draftHtml.set(html);
    this.editorChange = null;
    this.editor()?.setContent(html);
  }
  protected onEditorChange(change: EditorChange): void {
    this.editorChange = change;
    this.draftText.set(change.text);
  }
  /** The document as it stands: the editor's JSON if edited, else the template HTML. */
  private currentDocument(): { content_json?: Parameters<DraftsService['create']>[0]['content_json']; content_html: string } {
    if (this.editorChange) return { content_json: this.editorChange.json, content_html: this.editorChange.html };
    const json = this.editor()?.getJSON();
    const fallback = this.draftHtml();
    return { content_json: json ?? undefined, content_html: this.editor()?.getHTML() || (typeof fallback === 'string' ? fallback : '') };
  }
  private async createDraftFromBuilder(): Promise<{ id: string }> {
    const custom = this.selectedWordTemplate();
    if (custom) {
      let created = await firstValueFrom(this.drafts.createFromTemplate(custom.id, {
        title: this.cleanFilename(this.draftFileName),
        matter_id: this.matterId(),
        client_id: this.client()?.id ?? null,
        values: this.draftValues(),
      }));
      const current = this.currentDocument();
      if (current.content_json) created = await firstValueFrom(this.drafts.update(created.id, current));
      return created;
    }
    return firstValueFrom(this.drafts.create({
      title: this.cleanFilename(this.draftFileName),
      language: this.language(),
      template_id: this.selectedTemplate().id,
      matter_id: this.matterId(),
      client_id: this.client()?.id ?? null,
      ...this.currentDocument(),
    }));
  }

  private async loadProfile(): Promise<void> {
    try { this.profile.set(await firstValueFrom(this.profiles.myProfile())); }
    catch { /* profile is optional for ordinary drafting */ }
  }

  private judicialDefaults(): Record<string, string> {
    const p = this.profile();
    const court = p?.judicial_court_name ?? '';
    const place = [p?.judicial_district, p?.judicial_state].filter(Boolean).join(', ');
    return {
      date: todayDdMmYyyy(), orderDate: todayDdMmYyyy(),
      court, place,
      coram: [p?.designation, this.auth.user()?.full_name].filter(Boolean).join(' '),
      judgeName: this.auth.user()?.full_name ?? '',
      judgeDesignation: p?.designation ?? '',
      matterTitle: this.matterTitle() ?? '',
    };
  }

  protected async fetchCaseForOrder(): Promise<void> {
    const cnr = this.cnrNumber.trim();
    if (!cnr) { this.notify.error('Enter the 16-character CNR number.'); return; }
    this.ecourtsLoading.set(true);
    try {
      const item = await firstValueFrom(this.matters.ecourtsLookup({ cnr_number: cnr }));
      this.ecourtsCase.set(item);
      const applicants = item.parties.filter((party) => /petitioner|appellant|applicant|complainant/i.test(party.role)).map((party) => party.name).join(', ');
      const respondents = item.parties.filter((party) => /respondent|defendant|accused/i.test(party.role)).map((party) => party.name).join(', ');
      const appearances = item.advocates.map((advocate) => `${advocate.name} for ${advocate.appears_for}`).join('; ');
      const caseNumber = item.registration_number || item.case_number || [item.case_type, item.case_number, item.case_year].filter(Boolean).join(' ');
      this.draftValues.update((current) => ({
        ...current,
        court: item.court_establishment || current['court'] || '',
        place: [item.district, item.state].filter(Boolean).join(', ') || current['place'] || '',
        caseNumber: caseNumber || item.cnr_number || '',
        cnr: item.cnr_number || current['cnr'] || '',
        matterTitle: item.cause_title || current['matterTitle'] || '',
        firstParty: applicants || item.parties[0]?.name || '',
        secondParty: respondents || item.parties[1]?.name || '',
        coram: item.coram || current['coram'] || '',
        appearances,
        nextDate: item.next_hearing_date || '',
      }));
      this.refreshDraft();
      this.notify.success('Case header filled from the configured eCourts source. Verify it before signing.');
    } catch { /* provider/interceptor gives the configured-provider message */ }
    finally { this.ecourtsLoading.set(false); }
  }

  private async loadMatterForOrder(matterId: string): Promise<void> {
    try {
      const matter: MatterDetail = await firstValueFrom(this.matters.get(matterId));
      const applicants = matter.parties.filter((party) => party.side === 'ours').map((party) => party.name).join(', ');
      const respondents = matter.parties.filter((party) => party.side === 'opposing').map((party) => party.name).join(', ');
      const appearances = matter.advocates.map((advocate) => `${advocate.name}${advocate.party_represented ? ` for ${advocate.party_represented}` : ''}`).join('; ');
      this.draftValues.update((current) => ({
        ...current,
        court: matter.court_establishment || matter.court || current['court'] || '',
        place: [matter.district, matter.state].filter(Boolean).join(', ') || current['place'] || '',
        caseNumber: matter.registration_number || matter.case_number || matter.matter_number,
        cnr: matter.cnr_number || current['cnr'] || '',
        matterTitle: matter.cause_title || matter.title,
        firstParty: applicants,
        secondParty: respondents,
        coram: matter.coram || current['coram'] || '',
        appearances,
        nextDate: matter.next_hearing_date || '',
      }));
      this.refreshDraft();
    } catch { /* the order can still be drafted manually */ }
  }

  private async loadWordTemplates(): Promise<void> {
    this.templatesLoading.set(true);
    try { this.wordTemplates.set(await firstValueFrom(this.drafts.templates())); }
    catch { /* handled */ } finally { this.templatesLoading.set(false); }
  }
  protected async onTemplateUpload(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0]; input.value = '';
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.docx')) { this.notify.error('Choose a .docx Microsoft Word file.'); return; }
    this.uploadingTemplate.set(true);
    try {
      const created = await firstValueFrom(this.drafts.uploadTemplate(file, { language: this.language(), category: 'Firm templates' }));
      this.wordTemplates.update((items) => [created, ...items]);
      this.editingTemplate = created;
      this.showTemplateManager.set(true);
      this.notify.success(`${created.name} is ready as a drafting template. ${created.fields.length} form field${created.fields.length === 1 ? '' : 's'} found.`);
      await this.chooseWordTemplate(created);
    } catch { /* handled */ } finally { this.uploadingTemplate.set(false); }
  }
  protected async editWordTemplate(template: DraftTemplateSummary): Promise<void> {
    try { this.editingTemplate = await firstValueFrom(this.drafts.template(template.id)); this.showTemplateManager.set(true); }
    catch { /* handled */ }
  }
  protected addTemplateField(): void {
    if (!this.editingTemplate) return;
    const index = this.editingTemplate.fields.length + 1;
    this.editingTemplate.fields = [...this.editingTemplate.fields, { key: `field_${index}`, label: `Field ${index}`, token: `{{field_${index}}}`, type: 'text', required: false }];
  }
  protected removeTemplateField(index: number): void {
    if (this.editingTemplate) this.editingTemplate.fields = this.editingTemplate.fields.filter((_, i) => i !== index);
  }
  protected async saveTemplateSettings(): Promise<void> {
    const template = this.editingTemplate;
    if (!template) return;
    try {
      const updated = await firstValueFrom(this.drafts.updateTemplate(template.id, {
        name: template.name, description: template.description, category: template.category,
        language: template.language, fields: template.fields,
      }));
      this.editingTemplate = updated;
      this.wordTemplates.update((items) => items.map((item) => item.id === updated.id ? updated : item));
      if (this.selectedWordTemplate()?.id === updated.id) { this.selectedWordTemplate.set(updated); this.refreshDraft(); }
      this.notify.success('Template settings saved.');
    } catch { /* handled */ }
  }
  protected async deleteWordTemplate(template: DraftTemplateSummary): Promise<void> {
    if (!window.confirm(`Delete the template “${template.name}”? Existing drafts will remain.`)) return;
    try {
      await firstValueFrom(this.drafts.removeTemplate(template.id));
      this.wordTemplates.update((items) => items.filter((item) => item.id !== template.id));
      if (this.selectedWordTemplate()?.id === template.id) this.chooseTemplate(this.templates[0]);
      if (this.editingTemplate?.id === template.id) this.editingTemplate = null;
      this.notify.success('Template deleted.');
    } catch { /* handled */ }
  }
  protected async downloadWordTemplate(template: DraftTemplateSummary): Promise<void> {
    try { this.save(await firstValueFrom(this.drafts.downloadTemplate(template.id)), template.source_filename); }
    catch { /* handled */ }
  }
  private fillWordTemplate(content: EditorDoc, fields: DraftTemplateField[], values: Record<string, string>): EditorDoc {
    const output = structuredClone(content) as EditorDoc;
    const visit = (value: unknown): void => {
      if (Array.isArray(value)) { value.forEach(visit); return; }
      if (!value || typeof value !== 'object') return;
      const record = value as Record<string, unknown>;
      if (record['type'] === 'text' && typeof record['text'] === 'string') {
        let text = record['text'];
        for (const field of fields) text = text.split(field.token).join(values[field.key]?.trim() || field.token);
        record['text'] = text;
      }
      Object.values(record).forEach(visit);
    };
    visit(output);
    return output;
  }
  private editorText(content: EditorDoc): string {
    const lines: string[] = [];
    const visit = (value: unknown): void => {
      if (Array.isArray(value)) { value.forEach(visit); return; }
      if (!value || typeof value !== 'object') return;
      const record = value as Record<string, unknown>;
      if (record['type'] === 'text' && typeof record['text'] === 'string') lines.push(record['text']);
      else Object.values(record).forEach(visit);
    };
    visit(content);
    return lines.join(' ');
  }
  protected async openInEditor(): Promise<void> {
    this.savingDraft.set(true);
    try {
      const created = await this.createDraftFromBuilder();
      await this.router.navigate(['/app/documents/drafts', created.id]);
    } catch { /* handled */ } finally { this.savingDraft.set(false); }
  }
  protected async newBlankDraft(): Promise<void> {
    try {
      const created = await firstValueFrom(this.drafts.create({ title: 'Untitled document', language: this.language(), matter_id: this.matterId(), client_id: this.client()?.id ?? null }));
      await this.router.navigate(['/app/documents/drafts', created.id]);
    } catch { /* handled */ }
  }
  protected async showDrafts(): Promise<void> {
    this.view.set('drafts');
    this.draftsLoading.set(true);
    try { this.myDrafts.set(await firstValueFrom(this.drafts.list({ matterId: this.matterId(), clientId: this.listClientId() }))); }
    catch { /* handled */ } finally { this.draftsLoading.set(false); }
  }
  protected openDraft(d: DraftSummary): void { void this.router.navigate(['/app/documents/drafts', d.id]); }
  protected async deleteDraft(d: DraftSummary): Promise<void> {
    if (!window.confirm(`Delete "${d.title}"?`)) return;
    try { await firstValueFrom(this.drafts.remove(d.id)); this.myDrafts.update((items) => items.filter((x) => x.id !== d.id)); }
    catch { /* handled */ }
  }
  private cleanFilename(value: string): string { return (value.trim() || 'Legal draft').replace(/[\\/:*?"<>|]/g, '-'); }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      const query = this.search().trim();
      const clientId = this.listClientId();
      if (query) { this.subfolders.set([]); this.files.set(await firstValueFrom(this.docs.list({ q: query, matterId: this.matterId() ?? undefined, clientId }))); }
      else {
        const [folders, files] = await Promise.all([
          firstValueFrom(this.docs.folders(this.folder()?.id ?? null)),
          firstValueFrom(this.docs.list({ folderId: this.folder()?.id ?? null, matterId: this.matterId() ?? undefined, clientId })),
        ]);
        this.subfolders.set(folders); this.files.set(files);
      }
    } catch { /* handled */ } finally { this.loading.set(false); }
  }
  protected async enterFolder(folder: DocFolder): Promise<void> { this.folder.set(folder); this.search.set(''); await this.load(); }
  protected async goRoot(): Promise<void> { this.folder.set(null); this.search.set(''); await this.load(); }
  protected async runSearch(): Promise<void> { await this.load(); }
  protected async createFolder(): Promise<void> {
    const name = this.folderName.trim(); if (!name) return;
    try { const created = await firstValueFrom(this.docs.createFolder(name, this.folder()?.id ?? null)); this.subfolders.update((items) => [...items, created]); this.folderName = ''; this.showFolderInput.set(false); } catch { /* handled */ }
  }
  protected async onUpload(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement; const file = input.files?.[0]; input.value = ''; if (!file) return;
    try { const created = await firstValueFrom(this.docs.upload(file, file.name, this.folder()?.id ?? null, this.matterId() ?? undefined, this.client()?.id ?? null)); this.files.update((items) => [created, ...items]); this.notify.success(`${created.name} uploaded.`); } catch { /* handled */ }
  }
  /** Move a document to the current client, or take it off any client. */
  protected async assignClient(doc: DocFile, clientId: string | null): Promise<void> {
    try { this.patch(await firstValueFrom(this.docs.setClient(doc.id, clientId))); } catch { /* handled */ }
  }
  protected startNewVersion(doc: DocFile): void { this.versioning = doc; }
  protected async onNewVersion(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement; const file = input.files?.[0]; input.value = ''; const doc = this.versioning; this.versioning = null; if (!file || !doc) return;
    try { const updated = await firstValueFrom(this.docs.addVersion(doc.id, file)); this.patch(updated); this.openVersions.update((versions) => ({ ...versions, [doc.id]: undefined })); this.notify.success(`New version of ${updated.name} saved.`); } catch { /* handled */ }
  }
  protected async download(doc: DocFile): Promise<void> { try { this.save(await firstValueFrom(this.docs.download(doc.id)), doc.name); } catch { /* handled */ } }
  protected async downloadVersion(doc: DocFile, version: DocVersion): Promise<void> { try { this.save(await firstValueFrom(this.docs.downloadVersion(version.id)), `${doc.name} (v${version.version_no})`); } catch { /* handled */ } }
  protected async toggleVersions(doc: DocFile): Promise<void> {
    const open = this.openVersions(); if (open[doc.id] !== undefined) { this.openVersions.set({ ...open, [doc.id]: undefined }); return; }
    try { const versions = await firstValueFrom(this.docs.versions(doc.id)); this.openVersions.set({ ...this.openVersions(), [doc.id]: versions }); } catch { /* handled */ }
  }
  protected lockedByMe(doc: DocFile): boolean { return doc.locked_by === this.myId(); }
  protected async toggleLock(doc: DocFile): Promise<void> { try { this.patch(doc.locked_by ? await firstValueFrom(this.docs.checkin(doc.id)) : await firstValueFrom(this.docs.checkout(doc.id))); } catch { /* handled */ } }
  protected async remove(doc: DocFile): Promise<void> { try { await firstValueFrom(this.docs.remove(doc.id)); this.files.update((items) => items.filter((item) => item.id !== doc.id)); } catch { /* handled */ } }
  protected async showSignatures(): Promise<void> {
    this.view.set('signatures'); this.signingLoading.set(true);
    try { this.signatureEnvelopes.set(await firstValueFrom(this.docs.signatureEnvelopes())); }
    catch { /* handled */ } finally { this.signingLoading.set(false); }
  }
  protected startSignature(doc: DocFile): void {
    this.preparingDocument.set(doc); this.signatureTitle = doc.name; this.signerRows = [];
    this.signatureMessage = 'Please review and electronically sign this document.'; this.sequentialSigning = true;
    if (!this.teamPeople().length) void this.loadSigningPeople();
    this.addSigner('internal');
  }
  private async loadSigningPeople(): Promise<void> { try { this.teamPeople.set(await firstValueFrom(this.matters.people())); } catch { /* handled */ } }
  protected addSigner(kind: 'internal' | 'external'): void { this.signerRows = [...this.signerRows, { kind, user_id: null, name: '', email: '', designation: '' }]; }
  protected removeSigner(index: number): void { this.signerRows = this.signerRows.filter((_, i) => i !== index); }
  protected signerKind(index: number, kind: 'internal' | 'external'): void { this.signerRows[index] = { kind, user_id: null, name: '', email: '', designation: '' }; this.signerRows = [...this.signerRows]; }
  protected selectInternal(index: number, userId: string): void { const p = this.teamPeople().find((item) => item.id === userId); if (!p) return; this.signerRows[index] = { ...this.signerRows[index], user_id: p.id, name: p.full_name, email: p.email }; this.signerRows = [...this.signerRows]; }
  protected canSendSignature(): boolean { return !!this.preparingDocument() && this.signatureTitle.trim().length > 1 && this.signerRows.length > 0 && this.signerRows.every((s) => s.name.trim().length > 1 && /@/.test(s.email) && (s.kind === 'external' || !!s.user_id)); }
  protected async sendForSignature(): Promise<void> {
    const doc = this.preparingDocument(); if (!doc || !this.canSendSignature()) return;
    try { const created = await firstValueFrom(this.docs.prepareSignature(doc.id, { title: this.signatureTitle.trim(), message: this.signatureMessage.trim(), sequential: this.sequentialSigning, signers: this.signerRows })); this.signatureEnvelopes.update((items) => [created, ...items]); this.preparingDocument.set(null); this.notify.success('Document sent for electronic signature.'); await this.showSignatures(); } catch { /* handled */ }
  }
  protected myPendingStep(envelope: SignatureEnvelope): SignatureStep | undefined { return envelope.steps.find((s) => s.signer_user_id === this.myId() && s.status === 'pending'); }
  protected openSign(step: SignatureStep): void { this.signingStep.set(step); this.signingName = step.signer_name; this.signingDesignation = step.designation ?? ''; this.signingRemarks = ''; this.signingConsent = false; this.signingImage.set(''); }
  protected canApplySignature(): boolean { return !!this.signingStep() && this.signingName.trim().length > 1 && !!this.signingImage() && this.signingConsent; }
  protected async applySignature(): Promise<void> { const step = this.signingStep(); if (!step || !this.canApplySignature()) return; try { const updated = await firstValueFrom(this.docs.signStep(step.id, { signed_name: this.signingName, designation: this.signingDesignation, signature_data: this.signingImage(), remarks: this.signingRemarks, consent: this.signingConsent })); this.replaceEnvelope(updated); this.signingStep.set(null); this.notify.success('Electronic signature applied.'); } catch { /* handled */ } }
  protected async rejectSignature(step: SignatureStep): Promise<void> { const reason = window.prompt('Reason for rejecting this document:')?.trim(); if (!reason) return; try { this.replaceEnvelope(await firstValueFrom(this.docs.rejectStep(step.id, reason))); } catch { /* handled */ } }
  protected async cancelSignature(envelope: SignatureEnvelope): Promise<void> { if (!window.confirm(`Cancel the signature request for "${envelope.document_name}"?`)) return; try { this.replaceEnvelope(await firstValueFrom(this.docs.cancelSignature(envelope.id))); } catch { /* handled */ } }
  protected async downloadSigned(envelope: SignatureEnvelope, certificate = false): Promise<void> { try { const blob = await firstValueFrom(this.docs.signedDownload(envelope.id, certificate)); this.save(blob, certificate ? `${envelope.document_name}-signature-certificate.pdf` : `Signed-${envelope.document_name}`); } catch { /* handled */ } }
  protected async downloadSignatureSource(envelope: SignatureEnvelope): Promise<void> { try { this.save(await firstValueFrom(this.docs.signatureSource(envelope.id)), envelope.document_name); } catch { /* handled */ } }
  private replaceEnvelope(updated: SignatureEnvelope): void { this.signatureEnvelopes.update((items) => items.map((item) => item.id === updated.id ? updated : item)); }
  protected fileSize(bytes: number): string { if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / (1024 * 1024)).toFixed(1)} MB`; }
  private patch(updated: DocFile): void { this.files.update((items) => items.map((item) => item.id === updated.id ? updated : item)); }
  private save(blob: Blob, filename: string): void { void saveBlob(blob, filename); }
}

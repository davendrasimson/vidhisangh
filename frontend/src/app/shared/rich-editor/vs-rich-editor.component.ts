import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  ViewEncapsulation,
  computed,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Content, Editor, Extension, Node, mergeAttributes } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { TextStyleKit } from '@tiptap/extension-text-style';
import TextAlign from '@tiptap/extension-text-align';
import Highlight from '@tiptap/extension-highlight';
import { TableKit } from '@tiptap/extension-table';
import Image from '@tiptap/extension-image';
import Subscript from '@tiptap/extension-subscript';
import Superscript from '@tiptap/extension-superscript';
import { TaskItem, TaskList } from '@tiptap/extension-list';
import { CharacterCount, Placeholder } from '@tiptap/extensions';
import { DEFAULT_PAGE, EditorDoc, PAGE_SIZES_MM, PageSettings } from '@core/models/drafts.models';

/** What the editor reports after every change. */
export interface EditorChange {
  json: EditorDoc;
  html: string;
  text: string;
  words: number;
  characters: number;
}

/** Fonts offered in the toolbar; the DOCX export writes the first family name. */
export const EDITOR_FONTS: { label: string; value: string }[] = [
  { label: 'Times New Roman', value: "'Times New Roman', Times, serif" },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Garamond', value: "Garamond, 'EB Garamond', serif" },
  { label: 'Cambria', value: 'Cambria, Georgia, serif' },
  { label: 'Arial', value: 'Arial, Helvetica, sans-serif' },
  { label: 'Calibri', value: "Calibri, 'Segoe UI', sans-serif" },
  { label: 'Verdana', value: 'Verdana, Geneva, sans-serif' },
  { label: 'Courier New', value: "'Courier New', Courier, monospace" },
  { label: 'Noto Sans Devanagari', value: "'Noto Sans Devanagari', 'Mangal', sans-serif" },
  { label: 'Noto Sans Gurmukhi', value: "'Noto Sans Gurmukhi', 'Raavi', sans-serif" },
];
export const EDITOR_SIZES_PT = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48];
export const EDITOR_LINE_HEIGHTS = ['1', '1.15', '1.5', '2', '2.5', '3'];
const PALETTE = [
  '#000000', '#434343', '#666666', '#999999', '#b7b7b7', '#ffffff',
  '#980000', '#ff0000', '#ff9900', '#ffff00', '#00ff00', '#00ffff',
  '#4a86e8', '#0000ff', '#9900ff', '#ff00ff', '#1a56db', '#0e7c3a',
];
const HIGHLIGHTS = ['#fff176', '#a5d6a7', '#90caf9', '#f48fb1', '#ffcc80', '#e0e0e0'];

/** A hard page break — Word's Ctrl+Enter. Exported as a real page break. */
const PageBreak = Node.create({
  name: 'pageBreak',
  group: 'block',
  atom: true,
  selectable: true,
  parseHTML: () => [{ tag: 'div[data-page-break]' }],
  renderHTML: ({ HTMLAttributes }) => [
    'div', mergeAttributes(HTMLAttributes, { 'data-page-break': '', class: 'vs-page-break', contenteditable: 'false' }),
    ['span', {}, 'Page break'],
  ],
  addCommands() {
    return { setPageBreak: () => ({ commands }) => commands.insertContent({ type: 'pageBreak' }) };
  },
  addKeyboardShortcuts() {
    return { 'Mod-Enter': () => this.editor.commands.setPageBreak() };
  },
});

/** Paragraph-level line spacing and indent (Word's paragraph formatting). */
const ParagraphFormat = Extension.create({
  name: 'paragraphFormat',
  addGlobalAttributes() {
    return [{
      types: ['paragraph', 'heading'],
      attributes: {
        lineHeight: {
          default: null,
          parseHTML: (el) => el.style.lineHeight || null,
          renderHTML: (attrs) => (attrs['lineHeight'] ? { style: `line-height: ${attrs['lineHeight']}` } : {}),
        },
        indent: {
          default: 0,
          parseHTML: (el) => Number(el.getAttribute('data-indent') || 0),
          renderHTML: (attrs) =>
            attrs['indent'] ? { 'data-indent': attrs['indent'], style: `margin-left: ${attrs['indent'] * 10}mm` } : {},
        },
      },
    }];
  },
});

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    pageBreak: { setPageBreak: () => ReturnType };
  }
}

/**
 * The product's word processor: a TipTap/ProseMirror editor on a page-shaped
 * canvas with a Word-style toolbar. Emits the document as JSON (what the
 * server stores and exports) and HTML (what it shows elsewhere).
 */
@Component({
  selector: 'vs-rich-editor',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None, // ProseMirror's DOM is not ours to annotate
  imports: [FormsModule, MatIconModule],
  templateUrl: './vs-rich-editor.component.html',
  styleUrl: './vs-rich-editor.component.scss',
})
export class VsRichEditorComponent implements AfterViewInit, OnDestroy {
  /** Initial document (JSON or HTML). Later changes replace the content. */
  readonly content = input<EditorDoc | string | null>(null);
  readonly page = input<PageSettings>(DEFAULT_PAGE);
  readonly placeholder = input('Start typing…');
  /** Compact: shorter toolbar, no page chrome (for embedding in a form). */
  readonly compact = input(false, { transform: (v: unknown) => v !== false && v !== 'false' });
  readonly changed = output<EditorChange>();

  protected readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  protected editor: Editor | null = null;

  protected readonly fonts = EDITOR_FONTS;
  protected readonly sizes = EDITOR_SIZES_PT;
  protected readonly lineHeights = EDITOR_LINE_HEIGHTS;
  protected readonly palette = PALETTE;
  protected readonly highlights = HIGHLIGHTS;

  // Toolbar state, refreshed on every transaction.
  protected readonly tick = signal(0);
  protected readonly words = signal(0);
  protected readonly characters = signal(0);
  protected readonly openMenu = signal<'color' | 'highlight' | 'table' | 'find' | 'page' | null>(null);
  protected findText = '';
  protected replaceText = '';
  protected readonly findCount = signal<number | null>(null);
  protected tableRows = 3;
  protected tableCols = 3;

  protected readonly pageStyle = computed(() => {
    const p = this.page();
    let [w, h] = PAGE_SIZES_MM[p.size] ?? PAGE_SIZES_MM.A4;
    if (p.orientation === 'landscape') [w, h] = [h, w];
    const m = p.margins;
    return {
      width: `${w}mm`,
      minHeight: `${h}mm`,
      padding: `${m.top}mm ${m.right}mm ${m.bottom}mm ${m.left}mm`,
    };
  });

  ngAfterViewInit(): void {
    this.editor = new Editor({
      element: this.host().nativeElement,
      extensions: [
        StarterKit.configure({
          heading: { levels: [1, 2, 3, 4] },
          link: { openOnClick: false, autolink: true, defaultProtocol: 'https' },
        }),
        TextStyleKit.configure({ lineHeight: false }),
        ParagraphFormat,
        TextAlign.configure({ types: ['heading', 'paragraph'], defaultAlignment: 'left' }),
        Highlight.configure({ multicolor: true }),
        TableKit.configure({ table: { resizable: true, lastColumnResizable: false } }),
        Image.configure({ allowBase64: true, inline: false }),
        Subscript,
        Superscript,
        TaskList,
        TaskItem.configure({ nested: true }),
        PageBreak,
        Placeholder.configure({ placeholder: this.placeholder() }),
        CharacterCount,
      ],
      content: (this.content() ?? '') as Content,
      editorProps: { attributes: { class: 'vs-prose', spellcheck: 'true' } },
      onTransaction: () => this.tick.update((n) => n + 1),
      onUpdate: ({ editor }) => this.emit(editor),
    });
    this.emit(this.editor, false);
  }

  ngOnDestroy(): void {
    this.editor?.destroy();
  }

  private emit(editor: Editor, notify = true): void {
    const storage = editor.storage['characterCount'] as { words: () => number; characters: () => number };
    this.words.set(storage.words());
    this.characters.set(storage.characters());
    if (notify) {
      this.changed.emit({
        json: editor.getJSON() as EditorDoc,
        html: editor.getHTML(),
        text: editor.getText(),
        words: this.words(),
        characters: this.characters(),
      });
    }
  }

  // ── Public API for the page around the editor ──────────────────
  setContent(content: EditorDoc | string): void {
    this.editor?.commands.setContent(content as Content, { emitUpdate: false });
    if (this.editor) this.emit(this.editor, false);
  }
  getJSON(): EditorDoc | null { return (this.editor?.getJSON() as EditorDoc) ?? null; }
  getHTML(): string { return this.editor?.getHTML() ?? ''; }
  focus(): void { this.editor?.commands.focus(); }

  // ── Toolbar helpers ────────────────────────────────────────────
  protected is(name: string, attrs?: Record<string, unknown>): boolean {
    this.tick();
    return this.editor?.isActive(name, attrs) ?? false;
  }
  protected attr(mark: string, key: string): string {
    this.tick();
    return String((this.editor?.getAttributes(mark) ?? {})[key] ?? '');
  }
  protected can(action: 'undo' | 'redo'): boolean {
    this.tick();
    return action === 'undo' ? !!this.editor?.can().undo() : !!this.editor?.can().redo();
  }
  protected get chain() { return this.editor!.chain().focus(); }

  protected setBlock(value: string): void {
    if (value === 'p') this.chain.setParagraph().run();
    else this.chain.toggleHeading({ level: Number(value) as 1 | 2 | 3 | 4 }).run();
  }
  protected currentBlock(): string {
    this.tick();
    for (const level of [1, 2, 3, 4]) if (this.editor?.isActive('heading', { level })) return String(level);
    return 'p';
  }
  protected setFont(value: string): void { this.chain.setFontFamily(value).run(); }
  protected setSize(pt: string): void { this.chain.setFontSize(`${pt}pt`).run(); }
  protected currentSize(): string {
    const v = this.attr('textStyle', 'fontSize');
    return v ? v.replace('pt', '') : '12';
  }
  protected currentFont(): string {
    return this.attr('textStyle', 'fontFamily') || this.fonts[0].value;
  }
  protected setColor(c: string): void { this.chain.setColor(c).run(); this.openMenu.set(null); }
  protected setHighlight(c: string | null): void {
    (c ? this.chain.setHighlight({ color: c }) : this.chain.unsetHighlight()).run();
    this.openMenu.set(null);
  }
  protected setLineHeight(v: string): void {
    this.editor?.chain().focus().updateAttributes('paragraph', { lineHeight: v }).updateAttributes('heading', { lineHeight: v }).run();
  }
  protected currentLineHeight(): string {
    this.tick();
    return String(this.editor?.getAttributes('paragraph')['lineHeight'] ?? this.editor?.getAttributes('heading')['lineHeight'] ?? '1.15');
  }
  protected indent(delta: 1 | -1): void {
    const e = this.editor;
    if (!e) return;
    if (e.isActive('listItem') || e.isActive('taskItem')) {
      (delta > 0 ? e.chain().focus().sinkListItem(e.isActive('taskItem') ? 'taskItem' : 'listItem')
                 : e.chain().focus().liftListItem(e.isActive('taskItem') ? 'taskItem' : 'listItem')).run();
      return;
    }
    const type = e.isActive('heading') ? 'heading' : 'paragraph';
    const current = Number(e.getAttributes(type)['indent'] ?? 0);
    e.chain().focus().updateAttributes(type, { indent: Math.max(0, Math.min(8, current + delta)) }).run();
  }
  protected clearFormatting(): void { this.chain.unsetAllMarks().clearNodes().run(); }

  protected insertTable(): void {
    this.chain.insertTable({ rows: Math.max(1, this.tableRows), cols: Math.max(1, this.tableCols), withHeaderRow: true }).run();
    this.openMenu.set(null);
  }
  protected inTable(): boolean { return this.is('table'); }

  protected setLink(): void {
    const previous = this.editor?.getAttributes('link')['href'] as string | undefined;
    const url = window.prompt('Link address', previous ?? 'https://');
    if (url === null) return;
    if (!url.trim()) { this.chain.unsetLink().run(); return; }
    this.chain.extendMarkRange('link').setLink({ href: url.trim() }).run();
  }

  protected pickImage(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { window.alert('Images up to 2 MB, please.'); return; }
    const reader = new FileReader();
    reader.onload = () => this.chain.setImage({ src: String(reader.result), alt: file.name }).run();
    reader.readAsDataURL(file);
  }

  protected insertDate(): void {
    const d = new Date();
    const text = `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
    this.chain.insertContent(text).run();
  }

  // ── Find & replace ─────────────────────────────────────────────
  private matches(): { from: number; to: number }[] {
    const e = this.editor;
    const needle = this.findText.trim().toLowerCase();
    if (!e || !needle) return [];
    const out: { from: number; to: number }[] = [];
    e.state.doc.descendants((node, pos) => {
      if (!node.isText || !node.text) return;
      const hay = node.text.toLowerCase();
      let i = hay.indexOf(needle);
      while (i >= 0) {
        out.push({ from: pos + i, to: pos + i + needle.length });
        i = hay.indexOf(needle, i + needle.length);
      }
    });
    return out;
  }
  protected findNext(): void {
    const e = this.editor;
    const all = this.matches();
    this.findCount.set(all.length);
    if (!e || !all.length) return;
    const after = all.find((m) => m.from > e.state.selection.from) ?? all[0];
    e.chain().focus().setTextSelection(after).scrollIntoView().run();
  }
  protected replaceOne(): void {
    const e = this.editor;
    if (!e) return;
    const { from, to } = e.state.selection;
    const selected = e.state.doc.textBetween(from, to).toLowerCase();
    if (selected && selected === this.findText.trim().toLowerCase()) {
      e.chain().focus().insertContentAt({ from, to }, this.replaceText).run();
    }
    this.findNext();
  }
  protected replaceAll(): void {
    const e = this.editor;
    const all = this.matches().reverse(); // from the end, so positions stay valid
    if (!e || !all.length) return;
    let chain = e.chain().focus();
    for (const m of all) chain = chain.insertContentAt(m, this.replaceText);
    chain.run();
    this.findCount.set(0);
  }

  protected toggleMenu(name: 'color' | 'highlight' | 'table' | 'find' | 'page'): void {
    this.openMenu.set(this.openMenu() === name ? null : name);
  }

  protected onKeydown(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
      event.preventDefault();
      this.openMenu.set('find');
    }
  }
}

import {
  AfterViewInit, ChangeDetectionStrategy, Component, ElementRef, OnDestroy, ViewEncapsulation,
  inject, output, signal, viewChild,
} from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { firstValueFrom } from 'rxjs';
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { Placeholder } from '@tiptap/extensions';
import { NetworkService } from '@core/services/network.service';
import { problemMessage } from '@core/http/problem-message';

export interface ComposerValue { html: string; text: string; imageIds: string[]; uploading: boolean; }

interface PendingImage { localUrl: string; id: string | null; error: string | null; }

const MAX_IMAGES = 4;
const MAX_SIDE = 2000;

/**
 * Rich post composer: grows with its content (paste a long article and it
 * expands), basic formatting (bold, italic, underline, heading, lists, quote,
 * link) and up to four photos. Photos are re-drawn as JPEG of at most 2000 px
 * before upload, which also drops the camera's EXIF/GPS data; the server
 * strips metadata again (backend app/modules/network/media.py).
 */
@Component({
  selector: 'app-post-composer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  imports: [MatIconModule],
  template: `
    <div class="vs-pc">
      <div class="vs-pc__toolbar" role="toolbar" aria-label="Formatting">
        @for (b of buttons; track b.label) {
          <button type="button" class="vs-pc__btn" [class.is-on]="active()[b.key]" [attr.aria-pressed]="!!active()[b.key]"
                  [attr.aria-label]="b.label" [title]="b.label" (mousedown)="$event.preventDefault()" (click)="b.run()">
            <mat-icon class="material-icons-outlined">{{ b.icon }}</mat-icon>
          </button>
        }
        <span class="vs-pc__sep"></span>
        <button type="button" class="vs-pc__btn vs-pc__btn--photo" [disabled]="images().length >= maxImages"
                aria-label="Add photos" title="Add photos (up to 4)" (click)="fileInput.click()">
          <mat-icon class="material-icons-outlined">add_photo_alternate</mat-icon><span>Photo</span>
        </button>
        <input #fileInput type="file" accept="image/*" multiple hidden (change)="onFiles(fileInput)" />
      </div>
      <div #host class="vs-pc__editor"></div>
      @if (images().length) {
        <div class="vs-pc__images">
          @for (img of images(); track img.localUrl; let i = $index) {
            <figure class="vs-pc__thumb" [class.is-busy]="!img.id && !img.error" [class.is-error]="!!img.error">
              <img [src]="img.localUrl" alt="Photo to post" />
              @if (!img.id && !img.error) { <span class="vs-pc__badge">Uploading…</span> }
              @if (img.error) { <span class="vs-pc__badge vs-pc__badge--error">{{ img.error }}</span> }
              <button type="button" class="vs-pc__remove" aria-label="Remove photo" (click)="removeImage(i)">
                <mat-icon class="material-icons-outlined">close</mat-icon>
              </button>
            </figure>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .vs-pc { border: 1px solid rgb(var(--vs-line)); border-radius: 12px; background: rgb(var(--vs-surface-sunken)); }
    .vs-pc:focus-within { border-color: rgb(var(--vs-brand)); }
    .vs-pc__toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; padding: 4px 6px; border-bottom: 1px solid rgb(var(--vs-line)); }
    .vs-pc__btn { display: inline-flex; align-items: center; gap: 4px; height: 32px; min-width: 32px; padding: 0 6px; border: 0; border-radius: 8px; background: transparent; color: rgb(var(--vs-text-muted)); cursor: pointer; font: 600 .85rem var(--vs-font-ui); }
    .vs-pc__btn mat-icon { width: 20px; height: 20px; font-size: 20px; }
    .vs-pc__btn:hover:not(:disabled) { background: rgb(var(--vs-surface-raised)); color: rgb(var(--vs-content)); }
    .vs-pc__btn.is-on { background: color-mix(in srgb, rgb(var(--vs-brand)) 14%, transparent); color: rgb(var(--vs-brand)); }
    .vs-pc__btn:disabled { opacity: .4; cursor: default; }
    .vs-pc__btn--photo { color: rgb(var(--vs-brand)); }
    .vs-pc__sep { flex: 1; }
    .vs-pc__editor .ProseMirror { min-height: 4.5rem; max-height: 70vh; overflow-y: auto; padding: .75rem .9rem; outline: none; color: rgb(var(--vs-content)); line-height: 1.6; word-break: break-word; }
    .vs-pc__editor .ProseMirror p.is-editor-empty:first-child::before { content: attr(data-placeholder); float: left; height: 0; pointer-events: none; color: rgb(var(--vs-text-muted)); }
    .vs-pc__images { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 8px; padding: 0 .75rem .75rem; }
    .vs-pc__thumb { position: relative; margin: 0; aspect-ratio: 1; overflow: hidden; border-radius: 10px; border: 1px solid rgb(var(--vs-line)); }
    .vs-pc__thumb img { width: 100%; height: 100%; object-fit: cover; }
    .vs-pc__thumb.is-busy img { opacity: .55; }
    .vs-pc__thumb.is-error { border-color: rgb(var(--vs-danger)); }
    .vs-pc__badge { position: absolute; left: 4px; bottom: 4px; right: 4px; padding: 2px 6px; border-radius: 6px; background: rgb(0 0 0 / .6); color: #fff; font-size: .7rem; }
    .vs-pc__badge--error { background: rgb(var(--vs-danger)); }
    .vs-pc__remove { position: absolute; top: 4px; right: 4px; display: grid; place-items: center; width: 24px; height: 24px; border: 0; border-radius: 999px; background: rgb(0 0 0 / .6); color: #fff; cursor: pointer; }
    .vs-pc__remove mat-icon { width: 16px; height: 16px; font-size: 16px; }
  `],
})
export class PostComposerComponent implements AfterViewInit, OnDestroy {
  private readonly net = inject(NetworkService);
  private readonly host = viewChild.required<ElementRef<HTMLElement>>('host');
  private editor: Editor | null = null;

  readonly changed = output<ComposerValue>();
  protected readonly maxImages = MAX_IMAGES;
  protected readonly images = signal<PendingImage[]>([]);
  protected readonly active = signal<Record<string, boolean>>({});

  protected readonly buttons = [
    { key: 'bold', icon: 'format_bold', label: 'Bold', run: () => this.chain().toggleBold().run() },
    { key: 'italic', icon: 'format_italic', label: 'Italic', run: () => this.chain().toggleItalic().run() },
    { key: 'underline', icon: 'format_underlined', label: 'Underline', run: () => this.chain().toggleUnderline().run() },
    { key: 'heading', icon: 'title', label: 'Heading', run: () => this.chain().toggleHeading({ level: 2 }).run() },
    { key: 'bulletList', icon: 'format_list_bulleted', label: 'Bulleted list', run: () => this.chain().toggleBulletList().run() },
    { key: 'orderedList', icon: 'format_list_numbered', label: 'Numbered list', run: () => this.chain().toggleOrderedList().run() },
    { key: 'blockquote', icon: 'format_quote', label: 'Quote', run: () => this.chain().toggleBlockquote().run() },
    { key: 'link', icon: 'link', label: 'Link', run: () => this.toggleLink() },
  ];

  ngAfterViewInit(): void {
    this.editor = new Editor({
      element: this.host().nativeElement,
      extensions: [
        StarterKit.configure({
          heading: { levels: [2, 3] },
          code: false, codeBlock: false, horizontalRule: false,
          link: { openOnClick: false, autolink: true, protocols: ['http', 'https', 'mailto'],
            HTMLAttributes: { rel: 'noopener noreferrer nofollow', target: '_blank' } },
        }),
        Placeholder.configure({ placeholder: 'Share an update, a judgment, or a question… Paste an article, add photos.' }),
      ],
      editorProps: { attributes: { 'aria-label': 'Write a post', role: 'textbox', 'aria-multiline': 'true' } },
      onUpdate: () => this.emit(),
      onSelectionUpdate: () => this.refreshActive(),
      onTransaction: () => this.refreshActive(),
    });
  }

  ngOnDestroy(): void {
    this.editor?.destroy();
    this.images().forEach(i => URL.revokeObjectURL(i.localUrl));
  }

  /** Empty the composer after publishing. */
  clear(): void {
    this.editor?.commands.clearContent(true);
    this.images().forEach(i => URL.revokeObjectURL(i.localUrl));
    this.images.set([]);
    this.emit();
  }

  private chain() { return this.editor!.chain().focus(); }

  private toggleLink(): void {
    if (!this.editor) return;
    if (this.editor.isActive('link')) { this.chain().unsetLink().run(); return; }
    const url = window.prompt('Link address (https://…)', 'https://');
    if (!url || !/^(https?:\/\/|mailto:)/i.test(url.trim())) return;
    this.chain().extendMarkRange('link').setLink({ href: url.trim() }).run();
  }

  private refreshActive(): void {
    const e = this.editor;
    if (!e) return;
    this.active.set(Object.fromEntries(this.buttons.map(b =>
      [b.key, b.key === 'heading' ? e.isActive('heading') : e.isActive(b.key)])));
  }

  private emit(): void {
    const e = this.editor;
    const images = this.images();
    this.changed.emit({
      html: e && !e.isEmpty ? e.getHTML() : '',
      text: e ? e.getText({ blockSeparator: '\n\n' }).trim() : '',
      imageIds: images.filter(i => i.id).map(i => i.id!),
      uploading: images.some(i => !i.id && !i.error),
    });
  }

  protected removeImage(index: number): void {
    const img = this.images()[index];
    if (img) URL.revokeObjectURL(img.localUrl);
    this.images.update(list => list.filter((_, i) => i !== index));
    this.emit();
  }

  protected async onFiles(input: HTMLInputElement): Promise<void> {
    const files = Array.from(input.files ?? []).slice(0, MAX_IMAGES - this.images().length);
    input.value = '';
    for (const file of files) {
      const entry: PendingImage = { localUrl: URL.createObjectURL(file), id: null, error: null };
      this.images.update(list => [...list, entry]);
      this.emit();
      void this.upload(file, entry);
    }
  }

  private async upload(file: File, entry: PendingImage): Promise<void> {
    const update = (patch: Partial<PendingImage>) =>
      this.images.update(list => list.map(i => (i === entry ? Object.assign(entry, patch) : i)));
    try {
      const blob = await toJpeg(file);
      const result = await firstValueFrom(this.net.uploadPostImage(blob));
      if (!this.images().includes(entry)) return; // removed while uploading
      update({ id: result.id });
    } catch (err) {
      update({ error: problemMessage(err, 'Could not add this photo.') });
    } finally {
      this.images.set([...this.images()]);
      this.emit();
    }
  }
}

/** Re-draw as JPEG, longest side at most 2000 px: smaller uploads, no EXIF/GPS. */
async function toJpeg(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file).catch(() => { throw new Error('This file is not a photo the app can read.'); });
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#ffffff'; // transparent PNGs get a white background
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob(b => (b ? resolve(b) : reject(new Error('Could not prepare this photo.'))), 'image/jpeg', 0.85));
}

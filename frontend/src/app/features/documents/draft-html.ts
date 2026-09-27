/**
 * Turn a template's plain-text draft (see `renderDraft`) into editor HTML.
 *
 * The templates print court headings in capitals on their own line; those
 * become centred bold paragraphs. Everything else is a paragraph per line,
 * blank lines kept as spacing — the user formats the rest in the editor.
 */
export function draftTextToHtml(text: string): string {
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const lines = text.replace(/\r/g, '').split('\n');
  const out: string[] = [];
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { out.push('<p></p>'); continue; }
    const letters = line.replace(/[^A-Za-zऀ-੿]/g, '');
    const isHeading = letters.length >= 4 && line === line.toUpperCase() && line.length <= 90 && /[A-Z]/.test(line);
    if (isHeading) out.push(`<p style="text-align: center"><strong>${esc(line)}</strong></p>`);
    else out.push(`<p style="text-align: justify">${esc(line)}</p>`);
  }
  return out.join('');
}

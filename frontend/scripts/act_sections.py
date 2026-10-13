"""Extract sections (number, side-note heading, chapter, paragraphs) from an
official bare-act PDF, using word positions from poppler's `pdftotext -bbox-layout`.

Gazette layout: the body is one column; each section's heading is a side
note in the margin, level with the section's first line. Plain-text
conversion interleaves the two, so positions are used to keep them apart.
Section numbers are accepted only in sequence, so numbered clauses and
schedule items are never mistaken for a new section.
"""
import html
import re
import subprocess
from collections import Counter

LINE = re.compile(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', re.S)
WORD = re.compile(r'<word xMin="([\d.]+)" yMin="[\d.]+" xMax="([\d.]+)" yMax="[\d.]+">([^<]*)</word>')
PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
START = re.compile(r'^(\d{1,3})([A-Z]{0,2})\.\s*(?=\S)')
CHAPTER = re.compile(r'^CHAPTER\s*([IVXLC]+[A-Z]?)\b')


def _lines(pdf_path: str):
    out = subprocess.run(['pdftotext', '-bbox-layout', pdf_path, '-'], capture_output=True, text=True, check=True).stdout
    for page_no, (w, h, body) in enumerate(PAGE.findall(out)):
        rows = []
        for x0, y0, x1, y1, inner in LINE.findall(body):
            words = [(float(a), float(b), html.unescape(t)) for a, b, t in WORD.findall(inner)]
            text = ' '.join(w[2] for w in words).strip()
            if not text or set(text) <= set('_—-. '):
                continue
            rows.append({'x0': float(x0), 'y0': float(y0), 'x1': float(x1), 'text': text, 'words': words,
                         'page': page_no, 'h': float(h)})
        yield rows


def _classify(rows):
    """Split a page's rows into body rows and margin rows."""
    wide = [r for r in rows if r['x1'] - r['x0'] > 200]
    if not wide:
        return rows, [], 0.0
    left = Counter(round(r['x0']) for r in wide).most_common(1)[0][0]
    left = min(r['x0'] for r in wide if abs(r['x0'] - left) < 30)
    # The usual line end, not the widest line: a few lines overrun the column.
    right = Counter(round(r['x1']) for r in wide).most_common(1)[0][0]
    body, margin = [], []
    for r in rows:
        if r['y0'] < 75:                       # running head: page number, gazette title
            continue
        # Split by word: a side note can share a printed line with the body.
        inside = [w for w in r['words'] if w[1] > left - 3 and w[0] < right + 3]
        outside = [w for w in r['words'] if w not in inside]
        if outside:
            margin.append({**r, 'x0': outside[0][0], 'x1': outside[-1][1], 'text': ' '.join(w[2] for w in outside)})
        if inside:
            body.append({**r, 'x0': inside[0][0], 'x1': inside[-1][1], 'text': ' '.join(w[2] for w in inside)})
    return body, margin, left


def _notes(margin, start_ys=()):
    """Group margin rows into side notes: consecutive rows with small vertical
    gaps, split again wherever a section starts (each note is level with its
    section's first line, and close sections' notes otherwise run together)."""
    notes, cur = [], []
    for r in sorted(margin, key=lambda r: r['y0']):
        new_section = any(abs(r['y0'] - y) <= 4 for y in start_ys)
        if cur and (r['y0'] - cur[-1]['y0'] > 14 or new_section):
            notes.append(cur)
            cur = []
        cur.append(r)
    if cur:
        notes.append(cur)
    out = []
    for n in notes:
        text = ' '.join(r['text'] for r in n)
        # Citations of other Acts ("39 of 1925.") share the margin with headings.
        text = re.sub(r'\b\d+ of \d{4}\.?\s*', '', text).strip()
        if text:
            out.append({'y0': n[0]['y0'], 'text': text})
    return out


try:
    WORDS = {w.strip().lower() for w in open('/usr/share/dict/words', encoding='utf-8')}
except OSError:                       # extraction is a one-off; output is committed
    WORDS = set()


SMALL = {'of', 'and', 'the', 'to', 'in', 'as', 'for', 'on', 'by', 'or', 'at', 'a', 'an', 'with', 'from'}


def _title(caps: str) -> str:
    """'O F OFFENCES AGAINST PROPERTY' -> 'Of Offences Against Property'."""
    caps = re.sub(r'\s*,\s*', ', ', caps)
    caps = re.sub(r'\s+-\s*', '-', caps)
    caps = re.sub(r'\s+\.', '.', caps)
    tokens, merged = caps.split(), []
    for tok in tokens:
        prev = merged[-1] if merged else ''
        core = tok.rstrip(',.').lower()
        # Letter-spaced small capitals: 'O F' -> 'OF', 'C RIMINAL' -> 'CRIMINAL',
        # 'A IR' -> 'AIR', but 'OF A PERSON' keeps 'A' (judged by the word list).
        if len(prev) == 1 and prev.isalpha() and (
            len(tok) == 1 or (prev + core).lower() in WORDS and core not in WORDS or prev != 'A'
        ):
            merged[-1] += tok
        else:
            merged.append(tok)
    words = ' '.join(merged).lower().split()
    titled = ' '.join(w if i and w in SMALL else w[:1].upper() + w[1:] for i, w in enumerate(words))
    return titled.replace(' ,', ',')


def parse_pdf(pdf_path: str):
    sections, expected = [], 1
    current = None
    chapter, chapter_pending = '', False
    enacted = False
    for rows in _lines(pdf_path):
        if not rows:
            continue
        body, margin, left = _classify(rows)
        notes = _notes(margin, [r['y0'] for r in body if START.match(r['text'])])
        for r in sorted(body, key=lambda r: r['y0']):
            t = r['text']
            if not enacted and CHAPTER.match(t):
                chapter, chapter_pending = 'CHAPTER ' + CHAPTER.match(t).group(1), True
                continue
            if not enacted and chapter_pending and t.isupper():
                chapter, chapter_pending = f'{chapter} — {_title(t)}', False
                continue
            if not enacted:
                if re.search(r'it\s+enacted|enacted as follows', t, re.I):
                    enacted = True
                continue
            if CHAPTER.match(t):
                chapter, chapter_pending = 'CHAPTER ' + CHAPTER.match(t).group(1), True
                continue
            if re.match(r'^THE\s+(FIRST\s+|SECOND\s+)?SCHEDULE', t):
                break                                   # schedules are not sections
            if re.match(r'^[A-Z]\.\s*[—–-]', t):              # part heading inside a chapter
                continue
            if chapter_pending and t.isupper() and not START.match(t):
                chapter = f'{chapter} — {_title(t)}'
                chapter_pending = False
                continue
            chapter_pending = False
            m = START.match(t)
            if m and ((not m.group(2) and int(m.group(1)) == expected)
                      or (m.group(2) and int(m.group(1)) in (expected - 1, expected))):
                if not m.group(2):
                    expected += 1
                note = next((n for n in notes if -6 <= n['y0'] - r['y0'] <= 14), None)
                current = {
                    'number': m.group(1) + m.group(2),
                    'heading': re.sub(r'\s+', ' ', note['text']).strip().rstrip('.') if note else '',
                    'chapter': chapter,
                    'paragraphs': [t],
                }
                sections.append(current)
                continue
            if current is None:
                continue
            # A new paragraph starts at a clause marker, or on an indented line
            # after a line that ended a sentence or clause; otherwise the line
            # continues the wrapped sentence.
            indented = r['x0'] - left > 12
            centred = r['x1'] - r['x0'] < 160 and r['x0'] - left > 60
            prev = current['paragraphs'][-1]
            marker = re.match(r'^(\(|\d+\.|Explanation|Illustration|Provided|Exception|Note)', t)
            ended = re.search(r'[.;:—–]\s*$|[—–-]{2}$', prev)
            if marker or centred or (indented and ended):
                current['paragraphs'].append(t)
            else:
                prev = current['paragraphs'][-1]
                current['paragraphs'][-1] = prev[:-1] + t if prev.endswith('-') and not prev.endswith(' -') and t[:1].islower() else f'{prev} {t}'
    for sec in sections:
        # A short trailing line with no closing punctuation is a group heading
        # printed between sections ("Closely connected facts"), not section text.
        while len(sec['paragraphs']) > 1 and len(sec['paragraphs'][-1]) < 80 \
                and not re.search(r'[.;:—–)]\s*$', sec['paragraphs'][-1]):
            sec['paragraphs'].pop()
    return sections


CHAPTER_FIXES = {
    # Titles the PDF wraps or letter-spaces beyond what the rules recover.
    ('bns', 'CHAPTER VIII'): 'Of Offences Relating to the Army, Navy and Air Force',
    ('bns', 'CHAPTER XV'): 'Of Offences Affecting the Public Health, Safety, Convenience, Decency and Morals',
    ('bns', 'CHAPTER XIX'): 'Of Criminal Intimidation, Insult, Annoyance, Defamation, etc.',
    ('bnss', 'CHAPTER VIII'): 'Reciprocal Arrangements for Assistance in Certain Matters and Procedure for Attachment and Forfeiture of Property',
    ('bnss', 'CHAPTER XIX'): 'Trial Before a Court of Session',
}


def parse_act(act_id: str, pdf_path: str):
    sections = parse_pdf(pdf_path)
    for sec in sections:
        number = sec['chapter'].split(' — ')[0]
        if (act_id, number) in CHAPTER_FIXES:
            sec['chapter'] = f"{number} — {CHAPTER_FIXES[(act_id, number)]}"
    return sections


ACTS = {
    'bns': ('Bharatiya Nyaya Sanhita, 2023', 'BNS', 'https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf'),
    'bnss': ('Bharatiya Nagarik Suraksha Sanhita, 2023', 'BNSS', 'https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf'),
    'bsa': ('Bharatiya Sakshya Adhiniyam, 2023', 'BSA', 'https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf'),
}


if __name__ == '__main__':
    # Usage: python3 scripts/act_sections.py   (from frontend/)
    # One-off extraction; the JSON output is committed and read by
    # scripts/build-act-pages.mjs, so builds do not need poppler.
    import json
    import os
    os.makedirs('content/acts', exist_ok=True)
    for act_id, (title, short, source) in ACTS.items():
        secs = parse_act(act_id, f'public/bare-acts/{act_id}.pdf')
        data = {'id': act_id, 'title': title, 'short': short, 'source': source, 'sections': secs}
        with open(f'content/acts/{act_id}.json', 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        print(act_id, len(secs), 'sections,', sum(1 for x in secs if not x['heading']), 'without heading')

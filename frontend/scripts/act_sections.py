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

# India Code stamps a rotated "India Code" watermark on every downloaded page; it
# comes out as huge two-letter words ('In', 'di', 'aC', 'od', 'e') that are dropped
# by their width (a real two-letter word is under 15 points wide).
WATERMARK = {'In', 'di', 'aC', 'od', 'e'}
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
            words = [(float(a), float(b), html.unescape(t)) for a, b, t in WORD.findall(inner)
                     if not (html.unescape(t) in WATERMARK and float(b) - float(a) > 15)]
            text = ' '.join(w[2] for w in words).strip()
            if not text or set(text) <= set('_—-. '):
                continue
            rows.append({'x0': float(x0), 'y0': float(y0), 'x1': float(x1), 'text': text, 'words': words,
                         'page': page_no, 'h': float(h)})
        yield rows


def _classify(rows, variant: bool = False):
    """Split a page's rows into body rows and margin rows."""
    wide = [r for r in rows if r['x1'] - r['x0'] > 200]
    if not wide:
        return rows, [], 0.0
    if variant:
        # Leftmost of the common line starts: the most common one can be the
        # paragraph indent (166 against a 142 margin in the Consumer Protection Act).
        left = min(x for x, _ in Counter(round(r['x0']) for r in wide).most_common(3))
        left = min(r['x0'] for r in wide if abs(r['x0'] - left) < 3)
    else:
        left = Counter(round(r['x0']) for r in wide).most_common(1)[0][0]
        left = min(r['x0'] for r in wide if abs(r['x0'] - left) < 30)
    # The usual line end, not the widest line: a few lines overrun the column.
    right = Counter(round(r['x1']) for r in wide).most_common(1)[0][0]
    body, margin = [], []
    for r in rows:
        # Running head (page number, gazette title); some Acts start body text
        # above y=75, so only header-looking rows are dropped.
        if r['y0'] < 75 and (not variant or ((re.search(r'GAZETTE|PART\s*II|P\s?ART|^Sec\.|^\[|^THE\b', r['text'])
                                             or len(r['text']) < 30) and not START.match(r['text']))):
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


def parse_pdf(pdf_path: str, variant: bool = False):
    sections, expected = [], 1
    current = None
    chapter, chapter_pending = '', False
    enacted = False
    for rows in _lines(pdf_path):
        if not rows:
            continue
        body, margin, left = _classify(rows, variant)
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


# 'N. Heading.—Text'; old typewriter text sometimes drops the full stop ('17 "Government".--').
INLINE = re.compile(r'^(\d{1,3})([A-Z]{0,3})(?:\s*\.\s*|\s+(?=["“A-Z\[]))(.*)$')
HEAD_SPLIT = re.compile(r'^(.{2,240}?[.\]]["”]?)\s*[—–―-]{1,2}\s*(.*)$')
# Headings printed without the closing full stop ('65. Hours for presentment—Presentment
# for payment…'): a short capitalised run with no brackets or commas before an em dash.
HEAD_LOOSE = re.compile(r'^([A-Z“\[][^(),—–―]{1,110}?)\s*[—–―]\s*(.*)$')
FOOTNOTE_REF = re.compile(r'(?<![\w\d])\d{1,3}\*?(?=\[)|(?<![\w\d])\d{1,3}(?=\*{3,})')
# The India Code 'as on' editions set the reference off with a space ('4. 3 [(1)] Whoever');
# only those editions use this form, so a real 'Section 30 [note]' elsewhere is left alone.
FOOTNOTE_REF_SPACED = re.compile(r'(?<![\w\d])\d{1,3}\*?\s?(?=\[)|(?<![\w\d])\d{1,3}(?=\*{3,})')
INDIA_CODE_EDITIONS = {'pocso', 'rti', 'cheque'}
_footnote_ref = FOOTNOTE_REF


def _head(text: str):
    """Split 'Heading.—Body' (or the loose 'Heading—Body'), else None."""
    return HEAD_SPLIT.match(text) or HEAD_LOOSE.match(text)


# A page's amendment footnotes start at the first numbered line in India Code's
# footnote vocabulary; everything below it on that page is a footnote.
FOOTNOTE_START = re.compile(
    r'^\d{1,3}\.\s*(Subs\.|Ins\.|Rep\.|Added|Omitted|Renumbered|Cl\.|Clause|Ss?\.\s*\d|Sub-s|The (words|word|brackets|figures|letters?|proviso|Explanation|original)|Now\b|See\b|Vide\b|w\.e\.f|Am\. by|Amended|Inserted|Substituted|This (section|Act)|Certain words|Explanation|Proviso)',
    re.I)
# Footnote marks in front of a section line: '8*[4. ...', '[16. ...', '1*479. ...', '7 60. ...'.
AMENDMENT_NOTE = re.compile(
    r'^(\d{1,3}\.\s*)?(Subs\.?|Ins\.?|Rep\.|Omitted|Added|Am\.)\s+(by|vide|ibid)\b'
    r'|^\[?Vide\b'
    r'|^\d{1,3}\.\s*The (words?|brackets|figures|letters?|proviso)\b.*\b(omitted|subs|ins|rep)\.?\b'
    r'|^\d{1,3}\.\s.*\b(inserted|substituted|omitted|renumbered|added|repealed)\s+by\s+(the\s+)?(Act|A\.\s?O\.)', re.I)
LEAD_MARK = re.compile(r'^(\d{1,3}\*?)?\[\s*|^\d{1,3}\*(?=\d)|^\d{1,2}\s+(?=\d{1,3}\s*\.)')


def _clean_inline(text: str) -> str:
    """Drop India Code footnote reference numbers ('3*[extend' -> '[extend')."""
    return re.sub(r'\s{2,}', ' ', _footnote_ref.sub('', text)).strip()


def parse_inline_pdf(pdf_path: str, merge_fragments: bool = False, bare_headings: bool = False):
    """India Code layout: no side notes; each section opens 'N. Heading.—Text'
    (the heading may stand alone on the first line). Amendment footnotes sit
    left of the body column at the foot of the page and are skipped."""
    pages = [rows for rows in _lines(pdf_path) if rows]
    all_rows = [r for rows in pages for r in rows]
    wide = [r for r in all_rows if r['x1'] - r['x0'] > 300]
    # The body's left edge: the leftmost of the common line starts (the most
    # common one can be the paragraph indent, e.g. 108 against a 72 margin).
    left = min(x for x, _ in Counter(round(r['x0']) for r in wide).most_common(3)) if wide else 90
    sections, expected, current, pending_label, label_y = [], 1, None, None, -1.0
    pending_letter, letter_y = None, -1.0
    chapter, chapter_pending, enacted, title_just_set = '', False, False, False
    done = False
    for rows in pages:
        if done:
            break
        # Justified typewriter pages split a printed line into word fragments
        # at the same height: join them back, left to right.
        # Rows within 3pt of each other form one printed line (a heading can sit
        # 2pt above its number); read each line left to right.
        lines, line = [], []
        for r in sorted(rows, key=lambda r: r['y0']):
            if line and r['y0'] - line[0]['y0'] > 3:
                lines.append(line)
                line = []
            line.append(r)
        if line:
            lines.append(line)
        ordered = []
        for r in [r for ln in lines for r in sorted(ln, key=lambda r: r['x0'])]:
            if merge_fragments and ordered and abs(ordered[-1]['y0'] - r['y0']) < 1.5 and r['x0'] > ordered[-1]['x0']:
                last = ordered[-1]
                ordered[-1] = {**last, 'x1': r['x1'], 'text': f"{last['text']} {r['text']}"}
            else:
                ordered.append(r)
        in_footnotes = False
        for r in ordered:
            # Amendment footnotes run from the first footnote-style line to the
            # page number that closes the printed page (some PDFs stack several
            # printed pages on one sheet, so body text can follow).
            if not in_footnotes and r['y0'] > 0.2 * r['h'] and FOOTNOTE_START.match(r['text']):
                in_footnotes = True
            if in_footnotes:
                if re.fullmatch(r'\d{1,4}', r['text'].strip()):
                    in_footnotes = False
                continue
            t = LEAD_MARK.sub('', r['text'])            # '8*[4. Extension' -> '4. Extension'
            if r['x0'] < left - 8:                    # footnotes / page furniture
                continue
            if re.fullmatch(r'\d{1,3}', t):
                # A bare number at the left margin that is the next section is a
                # label (IT Act prints '2' + 'Definitions'); elsewhere it is a page number.
                if int(t) == expected and r['x0'] <= left + 5:
                    pending_label, label_y = expected, r['y0']
                continue
            if not enacted:
                if re.search(r'it\s+enacted|enacted as follows|enacted by parliament', t, re.I):
                    enacted = True
                continue
            if re.match(r'^THE\s+(FIRST\s+|SECOND\s+)?SCHEDULE', t):
                done = True                            # schedules are not sections
                break
            # A letter-spaced heading ('C H A P T E R V', 'O F P R E S E N T M E N T'):
            # join it; a chapter number is read, a title only while one is awaited.
            if re.fullmatch(r'[A-Z](?: [A-Z])+', t):
                joined = t.replace(' ', '')
                if joined.startswith('CHAPTER'):
                    t = 'CHAPTER ' + joined[7:]
                elif chapter_pending:
                    t = joined
                else:
                    continue
            # A part heading inside a chapter ('A.—PENETRATIVE SEXUAL ASSAULT …') is
            # not section text.
            if re.match(r'^[A-Z]\.\s*[—–―-]', t) and not re.search(r'[a-z]', t):
                continue
            if CHAPTER.match(t) or re.match(r'^PART\s+[IVXLC]+[A-Z]?\b', t):
                chapter, chapter_pending = t.split()[0].title().upper() + ' ' + t.split()[1].rstrip('.'), True
                if len(t.split()) > 2:
                    chapter, chapter_pending = f"{chapter} — {_title(' '.join(t.split()[2:]))}", False
                    title_just_set = True
                continue
            if chapter_pending and t.isupper() and not INLINE.match(t):
                chapter, chapter_pending, title_just_set = f'{chapter} — {_title(t)}', False, True
                continue
            # The second printed line of a chapter title that wrapped ('… IN THE' / 'ACCOUNTS'):
            # only when the first line is long or ends mid-phrase, so a short title followed
            # by a sub-heading ('Execution' / 'General') is left alone.
            if title_just_set:
                title_just_set = False
                title = chapter.split(' — ', 1)[-1]
                wrapped = len(title) >= 45 or title.split()[-1].lower() in {'and', 'of', 'the', 'in', 'for', 'to', 'or', 'by', 'with', 'on'}
                if wrapped and re.fullmatch(r"[A-Z][A-Z ,'&.-]{1,60}", t) and not INLINE.match(t):
                    chapter = f'{chapter} {_title(t)}'
                    continue
            chapter_pending = False
            # IT Act prints inserted sections as '66 A Heading': join the letter.
            spaced = re.match(r'^(\d{1,3}) ([A-Z]{1,2})\s+(\S.*)$', t)
            if spaced and int(spaced.group(1)) == expected - 1:
                rest = spaced.group(3)
                h = _head(rest)
                heading, body = (h.group(1), h.group(2)) if h else (rest, '')
                current = {'number': spaced.group(1) + spaced.group(2),
                           'heading': re.sub(r'\s+', ' ', heading).strip(' .[]'),
                           'chapter': chapter,
                           'paragraphs': [f'{spaced.group(1)}{spaced.group(2)}. {body}'.strip()]}
                sections.append(current)
                pending_label = None
                continue
            m = INLINE.match(t)
            num_ok = m and ((not m.group(2) and int(m.group(1)) == expected)
                            or (m.group(2) and int(m.group(1)) in (expected - 1, expected)))
            # The source occasionally misprints the number in the text line ('320.'
            # under a '330.' label); the label just above it is authoritative.
            if m and not num_ok and m.group(3) and pending_label == expected and not m.group(2):
                m = INLINE.match(f'{expected}. {m.group(3)}')
                num_ok = True
            if num_ok and m.group(3):
                if not m.group(2):
                    expected += 1
                pending_label = None
                rest = m.group(3)
                h = _head(rest)
                # Bare-heading layout (IT Act): '66D Punishment for ...' is the whole heading.
                if bare_headings and m.group(2) and not h and len(rest) < 200 and not rest.endswith((',', ';', ':', '—', '-')):
                    current = {'number': m.group(1) + m.group(2), 'heading': re.sub(r'\s+', ' ', rest).strip(' .[]'),
                               'chapter': chapter, 'paragraphs': [f'{m.group(1)}{m.group(2)}.']}
                    sections.append(current)
                    continue
                heading, body = (h.group(1), h.group(2)) if h else (rest if rest.endswith(('.', '.—')) and len(rest) < 200 else '', '' if rest.endswith('.') and len(rest) < 200 else rest)
                current = {
                    'number': m.group(1) + m.group(2),
                    'heading': re.sub(r'\s+', ' ', heading).strip(' .[]'),
                    'chapter': chapter,
                    'paragraphs': [f'{m.group(1)}{m.group(2)}. {body}'.strip()],
                }
                sections.append(current)
                continue
            # 'N to M. Rep. by ...': a whole range of sections was repealed.
            rng = re.match(r'^(\d{1,3})[A-Z]{0,3}\s+to\s+(\d{1,3})[A-Z]{0,3}\.\s*(Rep\.|\[?Omitted)?', t)
            if rng and int(rng.group(1)) == expected:
                if rng.group(3):
                    expected = int(rng.group(2)) + 1
                    current = None
                continue
            # Inserted-section label ('66C', '66E.') with its heading beside it on the
            # same printed line (IT Act).
            lettered = re.fullmatch(r'(\d{1,3})([A-Z]{1,2})\.?', t)
            if bare_headings and lettered and int(lettered.group(1)) == expected - 1:
                pending_letter, letter_y = lettered.group(1) + lettered.group(2), r['y0']
                continue
            if pending_letter and abs(r['y0'] - letter_y) < 3 and len(t) < 240 and t[:1].isupper():
                h = _head(t)
                heading, body = (h.group(1), h.group(2)) if h else (t, '')
                current = {'number': pending_letter, 'heading': re.sub(r'\s+', ' ', heading).strip(' .[]'),
                           'chapter': chapter, 'paragraphs': [f'{pending_letter}. {body}'.strip()]}
                sections.append(current)
                pending_letter = None
                continue
            pending_letter = None
            label = re.fullmatch(r'(\d{1,3})[A-Z]{0,3}\.', t)
            if label:
                pending_label = int(label.group(1))     # standalone 'N.' label above a section
                label_y = r['y0']
                continue
            # Label and a bare heading on one line (IT Act: '1.' + 'Short Title, Extent ...').
            if pending_label == expected and abs(r['y0'] - label_y) < 3 and not _head(t) \
                    and len(t) < 200 and t[:1].isupper() and not t.endswith((',', ';')):
                expected += 1
                current = {'number': str(pending_label), 'heading': re.sub(r'\s+', ' ', t).strip(' .[]'),
                           'chapter': chapter, 'paragraphs': [f'{pending_label}.']}
                sections.append(current)
                pending_label = None
                continue
            # Label and 'Heading.—Text' printed as separate fragments on one line.
            if pending_label == expected and abs(r['y0'] - label_y) < 3 and _head(t):
                m = INLINE.match(f'{expected}. {t}')
                expected += 1
                h = _head(t)
                current = {'number': str(pending_label), 'heading': re.sub(r'\s+', ' ', h.group(1)).strip(' .[]'),
                           'chapter': chapter, 'paragraphs': [f'{pending_label}. {h.group(2)}'.strip()]}
                sections.append(current)
                pending_label = None
                continue
            # A repealed section has only its label and '[Heading.] Rep. by ...':
            # count it, so the sequence carries on to the next live section.
            if pending_label == expected and (
                    re.match(r'^(\d{1,3}\*?)?\[?[^\]]*\]\s*[.—–-]*\s*(Rep\.|Omitted)', r['text'])
                    or re.match(r'^\(?\s*(Omitted|Repealed)\b', r['text'], re.I)):
                expected += 1
                pending_label = None
                current = None
                continue
            if current is None:
                continue
            prev = current['paragraphs'][-1]
            marker = re.match(r'^(\(|\d+\.|Explanation|Illustration|Provided|Exception|Note)', t)
            ended = re.search(r'[.;:—–―]\s*$|[—–-]{2}$', prev)
            indented = r['x0'] - left > 12
            centred = r['x1'] - r['x0'] < 160 and r['x0'] - left > 60
            if marker or centred or (indented and ended) or prev.endswith('. '):
                current['paragraphs'].append(t)
            else:
                current['paragraphs'][-1] = f'{prev} {t}'.strip()
    # Pass 1: recover headings that wrapped onto the next printed line, so
    # pass 2 can recognise the next section's heading run onto this one.
    for sec in sections:
        paras = [_clean_inline(p) for p in sec['paragraphs'] if p.strip()]
        sec['paragraphs'] = [p for p in paras if p and not re.fullmatch(r'\d{1,3}[A-Z]{0,3}\.?|\*+', p)]
        if not sec['heading'] and sec['paragraphs']:
            first = sec['paragraphs'][0]
            num = re.match(r'^\d{1,3}[A-Z]{0,3}\.?\s*', first)
            h = _head(first[num.end():] if num else first)
            if h and len(h.group(1)) < 240:
                sec['heading'] = re.sub(r'\s+', ' ', h.group(1)).strip(' .[]')
                sec['paragraphs'][0] = f"{sec['number']}. {h.group(2)}".strip()
    # Pass 2: trim what belongs to the next section or to the footnotes.
    out = []
    for i, sec in enumerate(sections):
        nxt = sections[i + 1]['heading'] if i + 1 < len(sections) else None
        paras = sec['paragraphs']
        # IPC-style layout repeats the next section's heading on its own line,
        # or runs it onto the end of this section's last paragraph.
        while paras and nxt and paras[-1].rstrip('.').strip() == nxt:
            paras.pop()
        if paras and nxt and paras[-1].rstrip('. ').endswith(nxt) and len(paras[-1]) > len(nxt) + 5:
            paras[-1] = paras[-1].rstrip('. ')[:-len(nxt)].rstrip()
            # ... sometimes after a group heading ('Of fraudulent deeds and dispositions of property').
            g = re.search(r'([.;:—)])\s+([A-Z][^.;:—]{3,90})$', paras[-1])
            if g:
                paras[-1] = paras[-1][:g.start(2)].rstrip()
            elif len(paras) > 1 and len(paras[-1]) < 100 and not re.search(r'[.;:—)]$', paras[-1]):
                paras.pop()                            # the group heading stood alone
        # Amendment notes that escaped the footnote filter (never the opening paragraph).
        sec['paragraphs'] = paras[:1] + [p for p in paras[1:] if p and not AMENDMENT_NOTE.match(p)]
        body = ' '.join(sec['paragraphs'])
        # Repealed or omitted sections carry no text worth a page.
        if re.match(r'^\d+[A-Z]*\.\s*(\[[^\]]*\]\s*[—–-]*\s*)?(Rep\.|\[?Omitted)', body) and len(body) < 260:
            continue
        out.append(sec)
    return out


CHAPTER_FIXES = {
    # Titles the PDF wraps or letter-spaces beyond what the rules recover.
    ('bns', 'CHAPTER VIII'): 'Of Offences Relating to the Army, Navy and Air Force',
    ('bns', 'CHAPTER XV'): 'Of Offences Affecting the Public Health, Safety, Convenience, Decency and Morals',
    ('bns', 'CHAPTER XIX'): 'Of Criminal Intimidation, Insult, Annoyance, Defamation, etc.',
    ('bnss', 'CHAPTER VIII'): 'Reciprocal Arrangements for Assistance in Certain Matters and Procedure for Attachment and Forfeiture of Property',
    ('bnss', 'CHAPTER XIX'): 'Trial Before a Court of Session',
    ('property', 'CHAPTER II'): 'Of Transfers of Property by Act of Parties',
    ('property', 'CHAPTER IV'): 'Of Mortgages of Immoveable Property and Charges',
    ('dv', 'CHAPTER III'): 'Powers and Duties of Protection Officers, Service Providers, etc.',
    ('pocso', 'CHAPTER II'): 'Sexual Offences Against Children',
    ('pocso', 'CHAPTER IV'): 'Abetment of and Attempt to Commit an Offence',
    ('pocso', 'CHAPTER VII'): 'Special Courts',
    ('pocso', 'CHAPTER VIII'): 'Procedure and Powers of Special Courts and Recording of Evidence',
    ('rti', 'CHAPTER I'): 'Preliminary',
    ('rti', 'CHAPTER III'): 'The Central Information Commission',
    ('cheque', 'CHAPTER II'): 'Of Notes, Bills and Cheques',
    ('cheque', 'CHAPTER III'): 'Parties to Notes, Bills and Cheques',
    ('cheque', 'CHAPTER V'): 'Of Presentment',
    ('cheque', 'CHAPTER VI'): 'Of Payment and Interest',
    ('cheque', 'CHAPTER IX'): 'Of Noting and Protest',
    ('cheque', 'CHAPTER X'): 'Of Reasonable Time',
    ('cheque', 'CHAPTER XII'): 'Of Compensation',
    ('cheque', 'CHAPTER XIII'): 'Special Rules of Evidence',
    ('cheque', 'CHAPTER XIV'): 'Of Crossed Cheques',
    ('cheque', 'CHAPTER XV'): 'Of Bills in Sets',
    ('cheque', 'CHAPTER XVI'): 'Of International Law',
    ('cheque', 'CHAPTER XVII'): 'Of Penalties in Case of Dishonour of Certain Cheques for Insufficiency of Funds in the Accounts',
}


def _tidy_chapter(act_id: str, chapter: str) -> str:
    number, _, name = chapter.partition(' — ')
    if (act_id, number) in CHAPTER_FIXES:
        return f"{number} — {CHAPTER_FIXES[(act_id, number)]}"
    tokens = name.split()
    # Letter-spaced capitals the rules could not rejoin, or a stray footnote number.
    fragments = [t for t in tokens if len(t) <= 2 and t.lower() not in {'of', 'to', 'an', 'by', 'in', 'on', 'or', 'as', 'at', 'a'}]
    if name and (re.fullmatch(r'[\d\s.]+', name) or (len(tokens) >= 3 and len(fragments) > 0.4 * len(tokens))):
        return number
    return chapter


def parse_act(act_id: str, pdf_path: str):
    sections = parse_pdf(pdf_path)
    for sec in sections:
        number = sec['chapter'].split(' — ')[0]
        if (act_id, number) in CHAPTER_FIXES:
            sec['chapter'] = f"{number} — {CHAPTER_FIXES[(act_id, number)]}"
    return sections


# Parser per Act: 'gazette' (side-note headings), 'gazette-variant' (same, with the
# leftmost-margin and loose running-head rules), 'inline' (India Code 'N. Heading.—'),
# 'inline-merge' (typewriter text split into word fragments), 'inline-bare' (number +
# heading with no '.—', IT Act). Acts not listed are
# not published: CrPC and IPC — India Code dropped both after their repeal and the
# bundled copies lost their line structure in conversion (see FUTURE_DELIVERABLES).
MODES = {
    'bns': 'gazette', 'bnss': 'gazette', 'bsa': 'gazette', 'companies': 'gazette',
    'consumer': 'gazette-variant', 'rera': 'gazette-variant',
    'ipc': 'inline-merge',
    'cpc': 'inline', 'contract': 'inline', 'evidence': 'inline', 'arbitration': 'inline',
    'property': 'inline', 'limitation': 'inline', 'posh': 'inline', 'special-marriage': 'inline',
    'hindu-marriage': 'inline', 'legal-aid': 'inline', 'succession': 'inline', 'dv': 'inline',
    'ibc': 'inline', 'it': 'inline-bare',
    # India Code 'as on' editions downloaded 31 Oct 2026 (indiacode.gov.in, DSpace API).
    'pocso': 'inline', 'rti': 'inline', 'cheque': 'inline',
}


def act_meta():
    """Title, short name, source and status from the app's own Act guides."""
    src = open('src/app/features/knowledge/data/acts.ts', encoding='utf-8').read()
    meta = {}
    for act_id in MODES:
        i = src.find(f"id: '{act_id}'")
        block = src[i:i + 6000]
        get = lambda key: (re.search(key + r":\s*'((?:[^'\\]|\\.)*)'", block) or [None, ''])[1].replace("\\'", "'")
        meta[act_id] = {'title': get('title'), 'short': get('short'), 'source': get('source'),
                        'status': get('status'), 'statusNote': get('statusNote'), 'area': get('area')}
    return meta


def extract(act_id: str):
    global _footnote_ref
    _footnote_ref = FOOTNOTE_REF_SPACED if act_id in INDIA_CODE_EDITIONS else FOOTNOTE_REF
    mode = MODES[act_id]
    path = f'public/bare-acts/{act_id}.pdf'
    if mode == 'gazette':
        secs = parse_act(act_id, path)
    elif mode == 'gazette-variant':
        secs = parse_pdf(path, variant=True)
    else:
        secs = parse_inline_pdf(path, merge_fragments=(mode == 'inline-merge'), bare_headings=(mode == 'inline-bare'))
    for sec in secs:
        sec['chapter'] = _tidy_chapter(act_id, sec['chapter'])
    return secs


if __name__ == '__main__':
    # Usage: python3 scripts/act_sections.py [act ...]   (from frontend/)
    # One-off extraction; the JSON output is committed and read by
    # scripts/build-act-pages.mjs, so builds do not need poppler.
    import json
    import os
    import sys
    os.makedirs('content/acts', exist_ok=True)
    meta = act_meta()
    for act_id in sys.argv[1:] or MODES:
        secs = extract(act_id)
        data = {'id': act_id, **meta[act_id], 'sections': secs}
        with open(f'content/acts/{act_id}.json', 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        print(f"{act_id:16} {len(secs):4} sections, {sum(1 for x in secs if not x['heading'])} without heading — {meta[act_id]['short']}: {meta[act_id]['title']} [{meta[act_id]['status']}]")

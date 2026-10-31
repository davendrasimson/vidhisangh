"""Regenerate the bare-act reader files for one or more Acts (from frontend/):

    python3 scripts/build-act-text.py pocso rti cheque

For each Act it writes public/bare-acts/text/<id>.txt (the title, then the
official PDF's plain text with the India Code watermark letters dropped),
updates the Act's entry in text/index.json (title, words, bytes) and replaces
its passages in text/search-index.json (one per section, from content/acts/
<id>.json, so the library search finds sections by number and heading).
The PDF manifest (public/bare-acts/manifest.json) is updated from the file
on disk; pass --source URL to record where the PDF came from.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess

TEXT_DIR = 'public/bare-acts/text'
WATERMARK_LINE = re.compile(r'^\s*(In|di|aC|od|e)\s*$')


def plain_text(pdf_path: str) -> str:
    out = subprocess.run(['pdftotext', pdf_path, '-'], capture_output=True, text=True, check=True).stdout
    # Drop the watermark letters and the punctuation-only columns of the front matter's abbreviation table.
    lines = [ln.rstrip() for ln in out.splitlines() if not WATERMARK_LINE.match(ln) and (re.search(r'[A-Za-z0-9\u0900-\u097F]', ln) or not ln.strip())]
    text = '\n'.join(lines)
    return re.sub(r'\n{3,}', '\n\n', text).strip() + '\n'


def passages(act: dict) -> list[dict]:
    out = [{'actId': act['id'], 'section': '', 'text': act['title']}]
    for sec in act['sections']:
        head = f"{sec['number']}. {sec['heading']}." if sec['heading'] else f"{sec['number']}."
        body = '\n'.join(sec['paragraphs'])
        if body.startswith(f"{sec['number']}."):
            body = body[len(sec['number']) + 1:].lstrip()
        out.append({'actId': act['id'], 'section': sec['number'], 'text': f"{head}\n{body}".strip()})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('acts', nargs='+')
    ap.add_argument('--source', help='official source URL to record in manifest.json (applies to every Act given)')
    args = ap.parse_args()

    index = json.load(open(f'{TEXT_DIR}/index.json', encoding='utf-8'))
    search = json.load(open(f'{TEXT_DIR}/search-index.json', encoding='utf-8'))
    manifest = json.load(open('public/bare-acts/manifest.json', encoding='utf-8'))
    today = dt.date.today().isoformat()

    for act_id in args.acts:
        act = json.load(open(f'content/acts/{act_id}.json', encoding='utf-8'))
        pdf = f'public/bare-acts/{act_id}.pdf'
        body = plain_text(pdf)
        text = f"{act['title']}\n\n{body}"
        with open(f'{TEXT_DIR}/{act_id}.txt', 'w', encoding='utf-8') as fh:
            fh.write(text)
        index[act_id] = {'title': act['title'], 'words': len(text.split()), 'bytes': len(text.encode('utf-8'))}
        search = [p for p in search if p['actId'] != act_id] + passages(act)
        entry = manifest.get(act_id, {})
        entry.update({'title': act['title'], 'retrieved_on': today, 'bytes': os.path.getsize(pdf)})
        if args.source:
            entry['official_source'] = args.source
        manifest[act_id] = entry
        print(f"{act_id:10} {index[act_id]['words']:>7} words, {len(act['sections'])} section passages")

    json.dump(index, open(f'{TEXT_DIR}/index.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    with open(f'{TEXT_DIR}/search-index.json', 'w', encoding='utf-8') as fh:
        json.dump(search, fh, ensure_ascii=False, separators=(',', ':'))
    json.dump(manifest, open('public/bare-acts/manifest.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()

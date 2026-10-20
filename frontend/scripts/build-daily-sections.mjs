// Writes backend/app/modules/network/daily_sections.json: the "Section of the
// day" pool for the official VidhiSangh feed posts (BNS, BNSS, BSA sections
// with a heading, their first paragraph and old-law equivalent).
//
//   node scripts/build-daily-sections.mjs   (from frontend/; rerun when content/ changes)
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname;
const OLD = { ipc: 'IPC', crpc: 'CrPC', evidence: 'Evidence Act' };
const out = [];
for (const id of ['bns', 'bnss', 'bsa']) {
  const act = JSON.parse(readFileSync(join(ROOT, `content/acts/${id}.json`), 'utf8'));
  const table = JSON.parse(readFileSync(join(ROOT, `content/correspondence/${id}.json`), 'utf8'));
  const old = {};
  for (const e of table.entries) {
    const n = e.new.match(/^\d+/)[0];
    for (const o of e.old) (old[n] ??= new Set()).add(o);
  }
  for (const sec of act.sections) {
    if (!sec.heading || !sec.paragraphs?.length) continue;
    let text = sec.paragraphs.join(' ').replace(/^\d+[A-Z]*\.\s*/, '').replace(/\s+/g, ' ').trim();
    if (text.length > 320) text = text.slice(0, 320).replace(/\s+\S*$/, '') + '…';
    const olds = [...(old[sec.number] ?? [])];
    out.push({
      act: id, short: act.short, section: sec.number, heading: sec.heading.replace(/\.$/, ''), text,
      old: olds.length ? `${OLD[table.old_act]} ${olds.join(', ')}` : '',
      url: `/acts/${id}/section-${sec.number.toLowerCase()}/`,
    });
  }
}
writeFileSync(join(ROOT, '../backend/app/modules/network/daily_sections.json'), JSON.stringify(out));
console.log(`daily sections: ${out.length}`);

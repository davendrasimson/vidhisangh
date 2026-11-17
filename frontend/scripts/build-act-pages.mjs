// Generates public, indexable bare-act pages from content/acts/*.json
// (extracted once by scripts/act_sections.py) into public/acts/, and rewrites
// public/sitemap.xml. Plain static HTML: fast, crawlable, no app bootstrap.
//
//   node scripts/build-act-pages.mjs        (from frontend/, before `ng build`)
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { I18N_JS } from './acts-i18n.mjs';

const ROOT = new URL('..', import.meta.url).pathname;
const SITE = 'https://vidhisangh.com';
const OUT = join(ROOT, 'public/acts');
// Every extracted Act; the three new criminal laws first, then by title.
const FIRST = ['bns', 'bnss', 'bsa'];
const ACT_IDS = readdirSync(join(ROOT, 'content/acts')).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, -5))
  .sort((a, b) => (FIRST.includes(b) - FIRST.includes(a)) || (FIRST.indexOf(a) - FIRST.indexOf(b)) || a.localeCompare(b));
const OLD_ACTS = {
  ipc: 'Indian Penal Code, 1860 (IPC)',
  crpc: 'Code of Criminal Procedure, 1973 (CrPC)',
  evidence: 'Indian Evidence Act, 1872',
};
const JOIN = '/auth/register?utm_source=bare_acts';
// Old <-> new law tables (BPRD), see scripts/law_correspondence.py.
const CORRESPONDENCE = ['bns', 'bnss', 'bsa'].map((id) => JSON.parse(readFileSync(join(ROOT, `content/correspondence/${id}.json`), 'utf8')));
// The BNSS First Schedule (classification of BNS offences), from scripts/bnss_schedule.py.
const OFFENCE_SCHEDULE_JSON = readFileSync(join(ROOT, 'content/bnss-first-schedule.json'), 'utf8');
const OFFENCE_SCHEDULE = JSON.parse(OFFENCE_SCHEDULE_JSON);
// Section 359 BNSS: the two compounding tables, from scripts/bnss_compounding.py; shipped inside the same data file.
const COMPOUNDING = JSON.parse(readFileSync(join(ROOT, 'content/bnss-compounding.json'), 'utf8')).rows;
const OFFENCE_DATA = { ...OFFENCE_SCHEDULE, compounding: COMPOUNDING };
const OFFENCE_SCHEDULE_URL = `/tools/bnss-first-schedule.json?v=${createHash('sha256').update(OFFENCE_SCHEDULE_JSON + JSON.stringify(COMPOUNDING)).digest('hex').slice(0, 10)}`;
const NEW_SHORT = { bns: 'BNS', bnss: 'BNSS', bsa: 'BSA' };
const OLD_SHORT = { ipc: 'IPC', crpc: 'CrPC', evidence: 'Evidence Act' };
const BPRD = 'https://bprd.mha.gov.in/page/documents_by_bprd';
// The converter's search box (pages allow scripts from this site only).
const CONVERTER_JS = `document.addEventListener('DOMContentLoaded', () => {
  const q = document.getElementById('convert-q');
  const rows = [...document.querySelectorAll('#convert-table tbody tr')];
  if (!q) return;
  const run = () => {
    const words = q.value.toLowerCase().trim().split(/\\s+/).filter(Boolean);
    for (const r of rows) r.hidden = !words.every((w) => r.dataset.q.includes(w));
  };
  q.addEventListener('input', run);
  const pre = new URLSearchParams(location.search).get('q');
  if (pre) { q.value = pre; run(); }
});
`;
// nginx caches .css for a year, so the link carries a content fingerprint.
const CSS = readFileSync(join(ROOT, 'scripts/acts.css'), 'utf8');
const CSS_URL = `/acts/acts.css?v=${createHash('sha256').update(CSS).digest('hex').slice(0, 10)}`;

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const base = (section) => section.toUpperCase().replace(/^SECTION\s*/, '').replace(/[\s(–-].*$/, '');

/** Old-law <-> new-law equivalents, keyed both ways ('bns:103' -> IPC 302,
 *  'ipc:302' -> BNS 103(1)): the full BPRD correspondence tables
 *  (content/correspondence/*.json, from scripts/law_correspondence.py), with
 *  the notes curated in the app (section-intelligence.ts) where they exist. */
function crossReferences() {
  const src = readFileSync(join(ROOT, 'src/app/features/knowledge/data/section-intelligence.ts'), 'utf8');
  const notes = {};
  const row = /\{ actId: '(\w+)', section: '([^']+)', correspondingActId: '(\w+)', correspondingSection: '([^']+)', subject: '([^']+)'(?:, note: '([^']+)')? \}/g;
  for (const m of src.matchAll(row)) if (m[6]) notes[`${m[1]}:${base(m[2])}`] = m[6];
  const refs = {};
  for (const table of CORRESPONDENCE) {
    for (const e of table.entries) {
      const key = `${table.new_act}:${base(e.new)}`;
      if (!e.old.length) {
        (refs[key] ??= []).push({ isNew: true, section: e.new, subject: e.subject });
        continue;
      }
      (refs[key] ??= []).push({ oldAct: table.old_act, oldSection: e.old_raw || e.old.join(', '), section: e.new, subject: e.subject });
      for (const o of e.old) {
        (refs[`${table.old_act}:${o}`] ??= []).push({
          newAct: table.new_act, newSection: e.new, oldSection: o, subject: e.subject, note: notes[`${table.old_act}:${o}`],
        });
      }
    }
  }
  return refs;
}

function page({ title, description, canonical, body, jsonLd }) {
  return `<!doctype html>
<html lang="en-IN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}" />
<meta name="robots" content="index, follow" />
<link rel="canonical" href="${canonical}" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="VidhiSangh" />
<meta property="og:title" content="${esc(title)}" />
<meta property="og:description" content="${esc(description)}" />
<meta property="og:url" content="${canonical}" />
<meta property="og:image" content="${SITE}/images/landing/og-feature.png" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="theme-color" content="#215dcc" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="stylesheet" href="${CSS_URL}" />
<script type="application/ld+json">${JSON.stringify(jsonLd)}</script>
</head>
<body>
<header class="top">
  <a class="brand" href="/"><img src="/brand-mark.svg" alt="" width="30" height="30" /><span>VidhiSangh</span></a>
  <nav><a class="join" href="${JOIN}" data-i18n>Join now</a><a class="signin" href="/auth/login" data-i18n>Sign in</a><button class="lang" id="vs-lang" type="button" lang="hi" aria-label="Switch language">हिन्दी</button></nav>
</header>
${body}
<footer>
  <p><a href="/acts/" data-i18n>Bare Acts</a> · <a href="/tools/" data-i18n>Free tools</a> · <a href="/">VidhiSangh</a> · <a href="/privacy" data-i18n>Privacy</a> · <a href="/terms" data-i18n>Terms</a></p>
  <p><span data-i18n>VidhiSangh is developed and managed by</span> <a href="/about">Simson Softwares Private Limited</a>. <span data-i18n>WhatsApp:</span> <a href="https://wa.me/917341100692" rel="noopener">+91 73411 00692</a></p>
  <p data-i18n>Text reproduced from the official publication for reference. Check the official source and later amendments before relying on it.</p>
</footer>
<script src="/acts/i18n.js" defer></script>
</body>
</html>
`;
}

function paragraphs(list) {
  return list.map((p) => {
    const cls = /^\(([a-z]{1,4}|[ivx]+)\)/.test(p) ? ' class="clause"' : /^(Explanation|Illustration|Provided|Exception)/.test(p) ? ' class="note"' : '';
    return `<p${cls}>${esc(p)}</p>`;
  }).join('\n');
}

function breadcrumbs(items) {
  return {
    '@type': 'BreadcrumbList',
    itemListElement: items.map(([name, url], i) => ({ '@type': 'ListItem', position: i + 1, name, item: SITE + url })),
  };
}

/** On a section page: what a member can do with this section, each a sign-up that lands on it. */
function sectionActions(act, number) {
  const n = encodeURIComponent(number);
  const actName = act.title.replace(/^(The )?(Indian )?/, '').replace(/,\s*\d{4}$/, '');
  const join = (next) => `/auth/register?utm_source=bare_acts_section&returnUrl=${encodeURIComponent(next)}`;
  const items = [
    ['Save it to your library', `Keep Section ${esc(number)} with your notes and find it again in one tap.`, join(`/app/knowledge/reader?act=${act.id}&section=${n}`)],
    ['See the judgments that apply it', `Supreme Court and High Court decisions citing Section ${esc(number)} ${esc(act.short)}.`, join(`/app/research?act=${encodeURIComponent(actName)}&section=${n}`)],
    ['Ask advocates about it', 'Discuss it in VidhiSangh groups, from Ask a Senior to your own High Court.', join('/app/groups')],
  ];
  // rel="nofollow" on every link into the app: crawlers have nothing to read there (17 Nov 2026).
  return `<aside class="section-actions"><h2>Use Section ${esc(number)} ${esc(act.short)} on VidhiSangh — free</h2><ul>${items.map(([t, d, href]) => `<li><a href="${href}" rel="nofollow"><b>${esc(t)}</b><span>${d}</span></a></li>`).join('')}</ul><p class="small">Already a member? <a href="/app/knowledge/reader?act=${act.id}&amp;section=${n}" rel="nofollow">Open it in the app</a>.</p></aside>`;
}

function cta(act, number) {
  const reader = `/app/knowledge/reader?act=${act.id}${number ? `&section=${encodeURIComponent(number)}` : ''}`;
  return `<aside class="cta">
  <div><strong>Read, search and save the full ${esc(act.short)} free</strong>
  <span>Plus 5.9 million Supreme Court and High Court judgments, and a professional network for India's legal fraternity.</span></div>
  <div class="cta-buttons"><a class="primary" href="${JOIN}" rel="nofollow">Join VidhiSangh free</a><a class="ghost" href="${reader}" rel="nofollow">Open in the app</a></div>
</aside>`;
}

const CONVERTERS = { ipc: 'ipc-to-bns', crpc: 'crpc-to-bnss', evidence: 'evidence-to-bsa' };
const natural = (a, b) => parseInt(a, 10) - parseInt(b, 10) || a.localeCompare(b);
const converterUrl = (oldAct, o) => `/acts/${CONVERTERS[oldAct]}/section-${o.toLowerCase()}/`;
const newLink = (newAct, section) => `<a href="/acts/${newAct}/section-${base(section).toLowerCase()}/">${esc(NEW_SHORT[newAct])} ${esc(section)}</a>`;
const SOURCE_NOTE = `Correspondence from the <a href="${BPRD}" rel="nofollow noopener" target="_blank">BPRD correspondence tables</a> (Ministry of Home Affairs). It shows where a provision went; wording, punishment and procedure may have changed, so read both sections.`;

/** On a BNS / BNSS / BSA section: the IPC / CrPC / Evidence Act provisions it replaces. */
function oldLawSection(act, sec, links) {
  const rows = links.filter((r) => r.oldAct || r.isNew);
  if (!rows.length) return '';
  const oldAct = CORRESPONDENCE.find((t) => t.new_act === act.id)?.old_act;
  const items = rows.map((r) => r.isNew
    ? `<li><b>${esc(act.short)} ${esc(r.section)}</b> — new provision, no ${esc(OLD_SHORT[oldAct])} equivalent.</li>`
    : `<li><b>${esc(act.short)} ${esc(r.section)}</b> ← ${r.oldSection.split(/,\s*|\s+and\s+/).map((o) => /^\d+[A-Z]*$/.test(o) ? `<a href="${converterUrl(r.oldAct, o)}">${esc(OLD_SHORT[r.oldAct])} ${esc(o)}</a>` : esc(`${OLD_SHORT[r.oldAct]} ${o}`)).join(', ')} — ${esc(r.subject)}</li>`);
  return `<section class="old-law"><h2 data-i18n>Old law equivalent</h2><ul>${items.join('')}</ul><p class="small">${SOURCE_NOTE} <a href="/acts/${CONVERTERS[oldAct]}/">${esc(OLD_SHORT[oldAct])} to ${esc(act.short)} converter</a>.</p></section>`;
}

/** On an IPC / Evidence Act section: where it is in the new law. */
function nowSection(act, sec, now) {
  if (!CONVERTERS[act.id]) return '';
  if (!now.length) {
    return `<section class="old-law"><h2 data-i18n>In the new law</h2><p>The BPRD correspondence table lists no ${esc(NEW_SHORT[CORRESPONDENCE.find((t) => t.old_act === act.id).new_act])} provision for this section.</p></section>`;
  }
  return `<section class="old-law"><h2 data-i18n>Now in the new law</h2><ul>${now.map((r) => `<li>${newLink(r.newAct, r.newSection)} — ${esc(r.subject)}${r.note ? `<br /><span class="small">${esc(r.note)}</span>` : ''}</li>`).join('')}</ul><p class="small"><a href="${converterUrl(act.id, base(sec.number))}">${esc(OLD_SHORT[act.id])} ${esc(sec.number)} in the ${esc(NEW_SHORT[now[0].newAct])}</a> · ${SOURCE_NOTE}</p></section>`;
}

function whatsappShare(text, url) {
  return `<a class="wa" href="https://wa.me/?text=${encodeURIComponent(`${text} ${SITE}${url}`)}" rel="noopener" target="_blank" data-i18n>Share on WhatsApp</a>`;
}

/** /acts/ipc-to-bns/ and one page per IPC section; same for CrPC and the Evidence Act. */
function converterPages(acts, refs, urls) {
  for (const table of CORRESPONDENCE) {
    const oldId = table.old_act, newId = table.new_act;
    const oldShort = OLD_SHORT[oldId], newShort = NEW_SHORT[newId];
    const slug = CONVERTERS[oldId];
    const oldAct = acts.find((a) => a.id === oldId);
    const oldHeadings = Object.fromEntries((oldAct?.sections ?? []).map((s) => [s.number, s.heading]));
    const numbers = new Set(table.entries.flatMap((e) => e.old));
    for (const s of oldAct?.sections ?? []) numbers.add(s.number);
    const sorted = [...numbers].sort(natural);
    const rowsFor = (o) => table.entries.filter((e) => e.old.includes(o));
    const listing = [];
    sorted.forEach((o, i) => {
      const rows = rowsFor(o);
      const url = `/acts/${slug}/section-${o.toLowerCase()}/`;
      // The table's subject first: the bundled IPC text predates the 2013
      // amendments, so some of its headings (e.g. 376A) are out of date.
      const heading = rows[0]?.subject || oldHeadings[o] || '';
      const targets = rows.map((e) => e.new);
      const targetText = targets.length > 1 ? `${newShort} Sections ${targets.slice(0, -1).join(', ')} and ${targets.at(-1)}` : targets.length ? `${newShort} Section ${targets[0]}` : '';
      listing.push({ o, url, heading, targets });
      const h1 = targets.length ? `${oldShort} Section ${o} is now ${targetText}` : `${oldShort} Section ${o} in the ${newShort}`;
      const share = targets.length ? `${oldShort} Section ${o}${heading ? ` (${heading})` : ''} is now ${targetText}.` : `${oldShort} Section ${o}: no ${newShort} equivalent listed.`;
      const prev = sorted[i - 1], next = sorted[i + 1];
      const body = `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/acts/" data-i18n>Bare Acts</a> › <a href="/acts/${slug}/">${esc(oldShort)} to ${esc(newShort)}</a> › <span>Section ${esc(o)}</span></nav>
<p class="eyebrow">${esc(oldShort)} to ${esc(newShort)} converter</p>
<h1>${esc(h1)}</h1>
${heading ? `<p class="lede">${esc(oldShort)} ${esc(o)}: ${esc(heading)}</p>` : ''}
${targets.length ? `<table class="convert"><thead><tr><th>${esc(newShort)}</th><th>Subject</th><th>${esc(oldShort)}</th></tr></thead><tbody>${rows.map((e) => `<tr><td>${newLink(newId, e.new)}</td><td>${esc(e.subject)}</td><td>${esc(e.old_raw || o)}</td></tr>`).join('')}</tbody></table>`
    : `<p>The BPRD correspondence table lists no ${esc(newShort)} provision for ${esc(oldShort)} section ${esc(o)}.</p>`}
<p class="actions">${whatsappShare(share, url)}${oldAct?.sections.some((s) => s.number === o) ? `<a class="ghost" href="/acts/${oldId}/section-${o.toLowerCase()}/">Read ${esc(oldShort)} ${esc(o)}</a>` : ''}${targets[0] ? `<a class="ghost" href="/acts/${newId}/section-${base(targets[0]).toLowerCase()}/">Read ${esc(newShort)} ${esc(base(targets[0]))}</a>` : ''}</p>
<p class="small">${SOURCE_NOTE}</p>
${cta({ id: newId, short: newShort }, targets[0] ? base(targets[0]) : '')}
<nav class="pager">${prev ? `<a href="/acts/${slug}/section-${prev.toLowerCase()}/">← ${esc(oldShort)} ${esc(prev)}</a>` : '<span></span>'}${next ? `<a class="next" href="/acts/${slug}/section-${next.toLowerCase()}/">${esc(oldShort)} ${esc(next)} →</a>` : ''}</nav>
</main>`;
      const description = targets.length
        ? `${oldShort} Section ${o}${heading ? ` (${heading})` : ''} corresponds to ${targetText} under the new criminal law. See the new section, compare both and share on WhatsApp.`
        : `${oldShort} Section ${o}${heading ? ` (${heading})` : ''}: the BPRD correspondence table lists no ${newShort} equivalent.`;
      mkdirSync(join(ROOT, 'public', url), { recursive: true });
      writeFileSync(join(ROOT, 'public', url, 'index.html'), page({
        title: targets.length ? `${oldShort} ${o} in ${newShort}: ${targetText.replace(`${newShort} `, '')}${heading ? ` — ${heading}` : ''} | VidhiSangh` : `${oldShort} ${o} in the ${newShort} | VidhiSangh`,
        description: description.slice(0, 158).replace(/\s+\S*$/, '') + (description.length > 158 ? '…' : ''),
        canonical: SITE + url,
        body,
        jsonLd: { '@context': 'https://schema.org', ...breadcrumbs([['Bare Acts', '/acts/'], [`${oldShort} to ${newShort}`, `/acts/${slug}/`], [`Section ${o}`, url]]) },
      }));
      urls.push([url, 'yearly', '0.6']);
    });

    const body = `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/acts/" data-i18n>Bare Acts</a> › <span>${esc(oldShort)} to ${esc(newShort)}</span></nav>
<p class="eyebrow">Old law to new law</p>
<h1>${esc(oldShort)} to ${esc(newShort)} converter</h1>
<p class="lede">Find the ${esc(newShort)} section for any ${esc(OLD_ACTS[oldId] || oldShort)} section: all ${sorted.length} sections, from the official BPRD correspondence table.</p>
<label class="search"><span data-i18n>Search by section number or subject</span><input id="convert-q" type="search" inputmode="search" placeholder="e.g. 420 or cheating" autocomplete="off" /></label>
<table class="convert" id="convert-table"><thead><tr><th>${esc(oldShort)}</th><th>${esc(newShort)}</th><th>Subject</th></tr></thead><tbody>
${listing.map((r) => `<tr data-q="${esc(`${oldShort} ${r.o} ${r.targets.join(' ')} ${r.heading}`.toLowerCase())}"><td><a href="${r.url}">${esc(r.o)}</a></td><td>${r.targets.length ? r.targets.map((t) => newLink(newId, t)).join(', ') : '—'}</td><td>${esc(r.heading)}</td></tr>`).join('\n')}
</tbody></table>
<p class="small">${SOURCE_NOTE}</p>
${cta({ id: newId, short: newShort }, '')}
</main>
<script src="/acts/converter.js" defer></script>`;
    mkdirSync(join(OUT, slug), { recursive: true });
    writeFileSync(join(OUT, slug, 'index.html'), page({
      title: `${oldShort} to ${newShort} converter — find the new section for every ${oldShort} section | VidhiSangh`,
      description: `${oldShort} to ${newShort}: the new-law section for each of ${sorted.length} ${oldShort} sections, searchable, from the official BPRD correspondence table. Free on VidhiSangh.`,
      canonical: `${SITE}/acts/${slug}/`,
      body,
      jsonLd: { '@context': 'https://schema.org', ...breadcrumbs([['Bare Acts', '/acts/'], [`${oldShort} to ${newShort}`, `/acts/${slug}/`]]) },
    }));
    urls.push([`/acts/${slug}/`, 'monthly', '0.9']);
  }
}

const TOOLS_OUT = join(ROOT, 'public/tools');
const SCHEDULE = JSON.parse(readFileSync(join(ROOT, 'content/limitation-schedule.json'), 'utf8'));
const TOOLS_JS = readFileSync(join(ROOT, 'scripts/tools.js'), 'utf8');
const TOOLS_JS_URL = `/tools/tools.js?v=${createHash('sha256').update(TOOLS_JS).digest('hex').slice(0, 10)}`;

function shortSubject(a) {
  const text = a.description.replace(/\s*Explanation\.?—.*$/, '').replace(/[,;:—–-]+$/, '');
  return text.length > 90 ? text.slice(0, 90).replace(/\s+\S*$/, '') + '…' : text.replace(/\.$/, '');
}

function limitationForm(selected) {
  const groups = [];
  for (const a of SCHEDULE) {
    const label = a.part || a.division;
    if (!groups.length || groups.at(-1).label !== label) groups.push({ label, items: [] });
    groups.at(-1).items.push(a);
  }
  return `<form class="tool" data-tool="limitation">
<label>Article of the Schedule<select name="article"><option value="">My own period (not listed)</option>${groups.map((g) => `<optgroup label="${esc(g.label)}">${g.items.map((a) => `<option value="${a.article}"${a.article === selected ? ' selected' : ''}>${a.article}. ${esc(shortSubject(a))} — ${esc(a.period)}</option>`).join('')}</optgroup>`).join('')}</select></label>
<p class="article-info small"></p>
<div class="clause-row" hidden><label>Which clause<select name="clause"></select></label></div>
<div class="custom-row row" hidden><label>Period<input name="n" inputmode="numeric" placeholder="e.g. 3" /></label><label>Unit<select name="unit"><option value="year">years</option><option value="month">months</option><option value="day">days</option></select></label></div>
<div class="row"><label>Period starts on (dd/mm/yyyy)<input name="start" inputmode="numeric" placeholder="dd/mm/yyyy" autocomplete="off" required /></label>
<label>Days to exclude (certified copy, s. 12)<input name="excluded" inputmode="numeric" placeholder="0" /></label></div>
<button type="submit" data-i18n>Calculate the last date</button>
</form>
<div class="tool-result" aria-live="polite"></div>
<script type="application/json" id="limitation-data">${JSON.stringify(SCHEDULE).replace(/</g, '\\u003c')}</script>
<script src="${TOOLS_JS_URL}" defer></script>`;
}

const TOOL_NOTE = '<p class="small">A calculator for quick reference, not legal advice. Check the Act, holidays of your court and any special law that sets its own period before relying on a date.</p>';

/** /tools/: limitation calculator (+ one page per Article) and default bail calculator. */
function toolPages(urls) {
  rmSync(TOOLS_OUT, { recursive: true, force: true });
  mkdirSync(TOOLS_OUT, { recursive: true });
  writeFileSync(join(TOOLS_OUT, 'tools.js'), TOOLS_JS);
  const write = (url, { title, description, body, crumbs }) => {
    mkdirSync(join(ROOT, 'public', url), { recursive: true });
    writeFileSync(join(ROOT, 'public', url, 'index.html'), page({
      title, description, canonical: SITE + url, body,
      jsonLd: { '@context': 'https://schema.org', ...breadcrumbs(crumbs) },
    }));
  };
  const crumbsBase = [['Free tools', '/tools/']];
  const limUrl = '/tools/limitation-calculator/';
  write(limUrl, {
    title: 'Limitation period calculator — Limitation Act, 1963, all 137 Articles | VidhiSangh',
    description: 'Find the last date to file a suit, appeal or application: pick the Article of the Limitation Act Schedule and the start date. Section 12 exclusions, Section 4 and the COVID period noted. Free.',
    crumbs: [...crumbsBase, ['Limitation calculator', limUrl]],
    body: `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/tools/" data-i18n>Free tools</a> › <span data-i18n>Limitation calculator</span></nav>
<p class="eyebrow">Free tool</p>
<h1>Limitation period calculator</h1>
<p class="lede">The last date to file a suit, appeal or application under the Limitation Act, 1963: choose the Article of the Schedule and the date the period begins.</p>
${limitationForm(0)}
${TOOL_NOTE}
<section class="toc"><h2>Periods of limitation, Article by Article</h2><ol>${SCHEDULE.map((a) => `<li><a href="${limUrl}article-${a.article}/"><b>${a.article}.</b> ${esc(shortSubject(a))} — ${esc(a.period)}</a></li>`).join('')}</ol></section>
${cta({ id: 'limitation', short: 'Limitation Act' }, '')}
</main>`,
  });
  urls.push([limUrl, 'monthly', '0.9']);
  for (const a of SCHEDULE) {
    const url = `${limUrl}article-${a.article}/`;
    const subject = shortSubject(a);
    const kind = /Appeals/.test(a.division) ? 'appeal' : /Applications/.test(a.division) ? 'application' : 'suit';
    write(url, {
      title: `Limitation for ${subject.charAt(0).toLowerCase() + subject.slice(1)}: ${a.period.replace(/\.$/, '').toLowerCase()} (Article ${a.article}) | VidhiSangh`.slice(0, 170),
      description: `Article ${a.article}, Limitation Act, 1963: ${subject}. Period: ${a.period} Time runs from: ${a.from}`.slice(0, 158).replace(/\s+\S*$/, '') + '…',
      crumbs: [...crumbsBase, ['Limitation calculator', limUrl], [`Article ${a.article}`, url]],
      body: `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/tools/" data-i18n>Free tools</a> › <a href="${limUrl}">Limitation calculator</a> › <span>Article ${a.article}</span></nav>
<p class="eyebrow">Limitation Act, 1963 · ${esc(a.division)}${a.part ? ` · ${esc(a.part)}` : ''}</p>
<h1>Article ${a.article}: ${esc(subject)}</h1>
<table class="convert facts"><tbody>
<tr><th>Description of ${kind}</th><td>${esc(a.description)}</td></tr>
<tr><th>Period of limitation</th><td><strong>${esc(a.period)}</strong></td></tr>
<tr><th>Time from which period begins to run</th><td>${esc(a.from)}</td></tr>
</tbody></table>
<h2>Calculate the last date</h2>
${limitationForm(a.article)}
${TOOL_NOTE}
<p class="actions">${whatsappShare(`Limitation for ${subject}: ${a.period} (Article ${a.article}, Limitation Act).`, url)}<a class="ghost" href="/acts/limitation/">Read the Limitation Act</a></p>
${cta({ id: 'limitation', short: 'Limitation Act' }, '')}
<nav class="pager">${a.article > 1 ? `<a href="${limUrl}article-${a.article - 1}/">← Article ${a.article - 1}</a>` : '<span></span>'}${a.article < SCHEDULE.length ? `<a class="next" href="${limUrl}article-${a.article + 1}/">Article ${a.article + 1} →</a>` : ''}</nav>
<p class="source">Source: <a href="/bare-acts/limitation.pdf" rel="nofollow">official text of the Limitation Act, 1963</a> (India Code).</p>
</main>`,
    });
    urls.push([url, 'yearly', '0.6']);
  }

  const bailUrl = '/tools/default-bail-calculator/';
  write(bailUrl, {
    title: 'Default bail calculator — Section 187(3) BNSS (167(2) CrPC), 60 and 90 days | VidhiSangh',
    description: 'When is the charge sheet due and when does the right to default bail arise? Enter the date of first remand: 60 or 90 days under Section 187(3) BNSS, counted as the Supreme Court held. Free.',
    crumbs: [...crumbsBase, ['Default bail calculator', bailUrl]],
    body: `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/tools/" data-i18n>Free tools</a> › <span data-i18n>Default bail calculator</span></nav>
<p class="eyebrow">Free tool</p>
<h1>Default bail calculator (Section 187(3) BNSS)</h1>
<p class="lede">The date the charge sheet is due, and the day the right to default bail arises if it is not filed.</p>
<form class="tool" data-tool="default-bail">
<label>Date of first remand to custody (dd/mm/yyyy)<input name="remand" inputmode="numeric" placeholder="dd/mm/yyyy" autocomplete="off" required /></label>
<fieldset><legend>The offence is punishable with</legend>
<label class="radio"><input type="radio" name="offence" value="90" checked /> death, imprisonment for life, or imprisonment of ten years or more — 90 days</label>
<label class="radio"><input type="radio" name="offence" value="60" /> any other punishment — 60 days</label></fieldset>
<button type="submit" data-i18n>Calculate</button>
</form>
<div class="tool-result" aria-live="polite"></div>
<script src="${TOOLS_JS_URL}" defer></script>
${TOOL_NOTE}
<p class="actions">${whatsappShare('Default bail calculator: 60/90 days under Section 187(3) BNSS.', bailUrl)}<a class="ghost" href="/acts/bnss/section-187/">Read Section 187 BNSS</a></p>
${cta({ id: 'bnss', short: 'BNSS' }, '187')}
</main>`,
  });
  urls.push([bailUrl, 'monthly', '0.8']);

  const interestUrl = '/tools/interest-calculator/';
  write(interestUrl, {
    title: 'Interest calculator — simple and compound interest between two dates (Section 34 CPC) | VidhiSangh',
    description: 'Interest on a sum between two dates: simple, or compounded monthly, quarterly or yearly. For money suits, decrees and invoices; Section 34 CPC noted. Free.',
    crumbs: [...crumbsBase, ['Interest calculator', interestUrl]],
    body: `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/tools/" data-i18n>Free tools</a> › <span data-i18n>Interest calculator</span></nav>
<p class="eyebrow">Free tool</p>
<h1>Interest calculator</h1>
<p class="lede">Interest on a sum between two dates — for money suits, decrees, cheque and invoice claims.</p>
<form class="tool" data-tool="interest">
<div class="row"><label>Amount (₹)<input name="principal" inputmode="decimal" placeholder="e.g. 5,00,000" required /></label>
<label>Rate (% a year)<input name="rate" inputmode="decimal" placeholder="e.g. 9" required /></label></div>
<div class="row"><label>From (dd/mm/yyyy)<input name="from" inputmode="numeric" placeholder="dd/mm/yyyy" autocomplete="off" required /></label>
<label>To (dd/mm/yyyy)<input name="to" inputmode="numeric" placeholder="dd/mm/yyyy" autocomplete="off" required /></label></div>
<label>Interest<select name="compound"><option value="0">Simple</option><option value="12">Compounded monthly</option><option value="4">Compounded quarterly</option><option value="1">Compounded yearly</option></select></label>
<button type="submit" data-i18n>Calculate interest</button>
</form>
<div class="tool-result" aria-live="polite"></div>
<script src="${TOOLS_JS_URL}" defer></script>
<p class="small">Under Section 34 of the Code of Civil Procedure the court decides the rate. From the date of the decree to payment it may not exceed six per cent a year, except where the liability arose out of a commercial transaction, when it may go up to the contractual rate or, if there is none, the rate at which nationalised banks lend for commercial transactions.</p>
${TOOL_NOTE}
<p class="actions">${whatsappShare('Interest calculator for advocates (simple and compound, between two dates):', interestUrl)}<a class="ghost" href="/acts/cpc/">Read the CPC</a></p>
${cta({ id: 'cpc', short: 'CPC' }, '')}
</main>`,
  });
  urls.push([interestUrl, 'monthly', '0.7']);

  // Offence screener: the BNSS First Schedule as a lookup (data file + page).
  writeFileSync(join(TOOLS_OUT, 'bnss-first-schedule.json'), JSON.stringify(OFFENCE_DATA));
  const offenceUrl = '/tools/offence-screener/';
  const examples = [['303(2)', 'Theft'], ['318(4)', 'Cheating (IPC 420)'], ['103', 'Murder'], ['IPC 498A', 'Cruelty by husband'], ['64', 'Rape'], ['351', 'Criminal intimidation']];
  write(offenceUrl, {
    title: 'Offence screener — is a BNS offence cognizable, bailable, which court tries it, default bail days | VidhiSangh',
    description: 'Type a BNS section, an IPC section or the name of the offence: punishment, cognizable or not, bailable or not, the court that tries it (BNSS First Schedule), with the arrest regime under Section 35 and default bail under Section 187(3) BNSS. Free.',
    crumbs: [...crumbsBase, ['Offence screener', offenceUrl]],
    body: `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/tools/" data-i18n>Free tools</a> › <span data-i18n>Offence screener</span></nav>
<p class="eyebrow">Free tool</p>
<h1>Offence screener (BNSS First Schedule)</h1>
<p class="lede">For any offence under the Bharatiya Nyaya Sanhita: the punishment, whether it is cognizable and bailable, the court that tries it — and what that means for arrest and default bail.</p>
<form class="tool" data-tool="offence" data-src="${OFFENCE_SCHEDULE_URL}">
<label>BNS section, IPC section or offence<input name="q" placeholder="e.g. 303(2), IPC 420, cheating" autocomplete="off" required /></label>
<button type="submit" data-i18n>Look up</button>
<p class="small">Try: ${examples.map(([q, label]) => `<a href="${offenceUrl}?q=${encodeURIComponent(q)}">${esc(q)} · ${esc(label)}</a>`).join(' · ')}</p>
</form>
<div class="tool-result" aria-live="polite"></div>
<script src="${TOOLS_JS_URL}" defer></script>
<p class="small">Part I of the First Schedule to the BNSS, 2023 (${OFFENCE_SCHEDULE.part_i.length} entries), from the Gazette text. For offences under other laws, Part II classifies by punishment: more than 7 years, life or death — cognizable, non-bailable, Court of Session; 3 to 7 years — cognizable, non-bailable, Magistrate of the first class; less than 3 years or fine only — non-cognizable, bailable, any Magistrate. Special laws (NDPS, UAPA, POCSO, SC/ST Act) set their own bail rules and default-bail periods. Compounding follows the two tables in Section 359 BNSS (${COMPOUNDING.filter((r) => r.part === 'victim').length} entries compoundable by the person affected, ${COMPOUNDING.filter((r) => r.part === 'court').length} only with the Court's permission); an offence in neither table is not compoundable, though the High Court may quash on settlement (Section 528).</p>
${TOOL_NOTE}
<p class="actions">${whatsappShare('Offence screener: cognizable? bailable? which court? default bail days — for any BNS section.', offenceUrl)}<a class="ghost" href="/acts/bnss/">Read the BNSS</a></p>
${cta({ id: 'bns', short: 'BNS' }, '')}
</main>`,
  });
  urls.push([offenceUrl, 'monthly', '0.8']);

  write('/tools/', {
    title: 'Free legal tools — limitation, default bail and interest calculators, offence screener, IPC to BNS | VidhiSangh',
    description: 'Free tools for advocates: limitation period calculator for all 137 Articles, default bail calculator under BNSS, offence screener from the BNSS First Schedule, interest calculator, and IPC to BNS, CrPC to BNSS and Evidence Act to BSA converters.',
    crumbs: crumbsBase,
    body: `<main>
<p class="eyebrow">Free tools</p>
<h1>Free tools for advocates</h1>
<div class="acts">
<a class="act" href="${limUrl}"><b>Limitation</b><span>Last date to file a suit, appeal or application, all 137 Articles</span><small>Calculator</small></a>
<a class="act" href="${bailUrl}"><b>Default bail</b><span>60 / 90 days under Section 187(3) BNSS</span><small>Calculator</small></a>
<a class="act" href="${interestUrl}"><b>Interest</b><span>Simple or compound interest between two dates</span><small>Calculator</small></a>
<a class="act" href="${offenceUrl}"><b>Offence screener</b><span>Cognizable? Bailable? Which court? Default bail days — any BNS section</span><small>Lookup</small></a>
${CORRESPONDENCE.map((t) => `<a class="act" href="/acts/${CONVERTERS[t.old_act]}/"><b>${esc(OLD_SHORT[t.old_act])} → ${esc(NEW_SHORT[t.new_act])}</b><span>Find the new section for any old one</span><small>Converter</small></a>`).join('')}
</div>
${cta({ id: 'bns', short: 'Acts' }, '')}
</main>`,
  });
  urls.push(['/tools/', 'monthly', '0.9']);
}

function build() {
  const refs = crossReferences();
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, 'acts.css'), CSS);
  writeFileSync(join(OUT, 'i18n.js'), I18N_JS);
  const urls = [];
  const acts = ACT_IDS.map((id) => JSON.parse(readFileSync(join(ROOT, `content/acts/${id}.json`), 'utf8')));

  for (const act of acts) {
    const actUrl = `/acts/${act.id}/`;
    urls.push([actUrl, 'monthly', '0.8']);
    const seen = new Set();
    act.sections = act.sections.filter((sec) => !seen.has(sec.number) && seen.add(sec.number));
    const label = (sec) => sec.heading ? `Section ${sec.number}: ${sec.heading}` : `Section ${sec.number}`;
    const repealed = act.status === 'repealed'
      ? `<p class="repealed"><strong>Repealed.</strong> ${esc(act.statusNote || 'This Act has been repealed.')}</p>` : '';
    act.sections.forEach((sec, i) => {
      const url = `${actUrl}section-${sec.number.toLowerCase()}/`;
      const prev = act.sections[i - 1];
      const next = act.sections[i + 1];
      const links = refs[`${act.id}:${base(sec.number)}`] ?? [];
      const now = links.filter((r) => r.newAct);
      const first = sec.paragraphs.join(' ').replace(/^\d+[A-Z]*\.\s*/, '');
      const description = `Section ${sec.number}, ${act.title} (${act.short})${sec.heading ? `: ${sec.heading}` : ''}. ${first}`.slice(0, 158).replace(/\s+\S*$/, '') + '…';
      const title = sec.heading
        ? `Section ${sec.number} ${act.short} — ${sec.heading} | ${act.title}`
        : `Section ${sec.number}, ${act.title} (${act.short}) | VidhiSangh`;
      const [chapterNo, chapterName = ''] = sec.chapter.split(' — ');
      const body = `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/acts/" data-i18n>Bare Acts</a> › <a href="${actUrl}">${esc(act.short)}</a>${chapterNo ? ` › <span>${esc(chapterNo.replace('CHAPTER', 'Chapter').replace('PART', 'Part'))}</span>` : ''}</nav>
<p class="eyebrow">${esc(act.title)}</p>
<h1>${esc(label(sec))}</h1>
${repealed}
${chapterNo ? `<p class="chapter">${esc(chapterNo.replace('CHAPTER', 'Chapter').replace('PART', 'Part'))}${chapterName ? ` — ${esc(chapterName)}` : ''}</p>` : ''}
<article class="text">
${paragraphs(sec.paragraphs)}
</article>
${oldLawSection(act, sec, links)}
${nowSection(act, sec, now)}
<p class="actions">${whatsappShare(`Section ${sec.number} ${act.short}${sec.heading ? ` — ${sec.heading}` : ''}:`, url)}</p>
${sectionActions(act, sec.number)}
<nav class="pager">${prev ? `<a href="${actUrl}section-${prev.number.toLowerCase()}/">← ${esc(label(prev))}</a>` : '<span></span>'}${next ? `<a class="next" href="${actUrl}section-${next.number.toLowerCase()}/">${esc(label(next))} →</a>` : ''}</nav>
<p class="source">Source: <a href="${act.source}" rel="nofollow noopener" target="_blank">official text of the ${esc(act.title)}</a>.</p>
</main>`;
      const jsonLd = {
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': 'Legislation',
            name: `Section ${sec.number}, ${act.title}${sec.heading ? ` — ${sec.heading}` : ''}`,
            legislationIdentifier: `${act.short} s. ${sec.number}`,
            legislationJurisdiction: 'IN',
            inLanguage: 'en-IN',
            url: SITE + url,
            isPartOf: { '@type': 'Legislation', name: act.title, url: SITE + actUrl },
          },
          breadcrumbs([['Bare Acts', '/acts/'], [act.short, actUrl], [`Section ${sec.number}`, url]]),
        ],
      };
      mkdirSync(join(ROOT, 'public', url), { recursive: true });
      writeFileSync(join(ROOT, 'public', url, 'index.html'), page({ title, description, canonical: SITE + url, body, jsonLd }));
      urls.push([url, 'yearly', '0.6']);
    });

    // Act contents page, grouped by chapter.
    const chapters = [];
    for (const sec of act.sections) {
      if (!chapters.length || chapters.at(-1).name !== sec.chapter) chapters.push({ name: sec.chapter, sections: [] });
      chapters.at(-1).sections.push(sec);
    }
    const body = `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/acts/" data-i18n>Bare Acts</a> › <span>${esc(act.short)}</span></nav>
<p class="eyebrow">Bare Act · ${act.sections.length} sections</p>
<h1>${esc(act.title)} (${esc(act.short)})</h1>
${repealed}
${cta(act, '')}
${chapters.map((c) => `<section class="toc"><h2>${esc((c.name || 'Sections').replace('CHAPTER', 'Chapter').replace('PART', 'Part'))}</h2><ol>${c.sections.map((s) => `<li><a href="${actUrl}section-${s.number.toLowerCase()}/"><b>${esc(s.number)}.</b> ${esc(s.heading || 'Section ' + s.number)}</a></li>`).join('')}</ol></section>`).join('\n')}
<p class="source">Source: <a href="${act.source}" rel="nofollow noopener" target="_blank">official text</a>.</p>
</main>`;
    const jsonLd = {
      '@context': 'https://schema.org',
      '@graph': [
        { '@type': 'Legislation', name: act.title, legislationIdentifier: act.short, legislationJurisdiction: 'IN', inLanguage: 'en-IN', url: SITE + actUrl },
        breadcrumbs([['Bare Acts', '/acts/'], [act.short, actUrl]]),
      ],
    };
    mkdirSync(join(OUT, act.id), { recursive: true });
    writeFileSync(join(OUT, act.id, 'index.html'), page({
      title: `${act.title} (${act.short}) — all ${act.sections.length} sections | VidhiSangh`,
      description: `Read the ${act.title} (${act.short}) section by section: all ${act.sections.length} sections with headings, chapter by chapter. Free on VidhiSangh.`,
      canonical: SITE + actUrl, body, jsonLd,
    }));
  }

  converterPages(acts, refs, urls);
  toolPages(urls);
  // The same tables for the in-app bare-act reader (a lazily loaded chunk).
  writeFileSync(join(ROOT, 'src/app/features/knowledge/data/correspondence-data.ts'),
    '// Generated by scripts/build-act-pages.mjs from content/correspondence/*.json — do not edit.\n'
    + '// [new section, subject, old sections, old section as printed]\n'
    + `export const CORRESPONDENCE: { newAct: string; oldAct: string; rows: [string, string, string[], string][] }[] = ${JSON.stringify(
      CORRESPONDENCE.map((t) => ({ newAct: t.new_act, oldAct: t.old_act, rows: t.entries.map((e) => [e.new, e.subject, e.old, e.old_raw]) })))};\n`
    + `/** Acts with public section pages at vidhisangh.com/acts/<id>/section-<n>/. */\nexport const PUBLISHED_ACTS: string[] = ${JSON.stringify(ACT_IDS)};\n`);
  writeFileSync(join(OUT, 'converter.js'), CONVERTER_JS);
  // The BNSS First Schedule for the in-app Act reader (another lazy chunk).
  writeFileSync(join(ROOT, 'src/app/features/knowledge/data/bnss-schedule-data.ts'),
    '// Generated by scripts/build-act-pages.mjs from content/bnss-first-schedule.json — do not edit.\n'
    + '// [BNS section, offence, punishment, cognizable, bailable, triable by]\n'
    + `export const BNSS_FIRST_SCHEDULE: [string, string, string, string, string, string][] = ${JSON.stringify(
      OFFENCE_SCHEDULE.part_i.map((r) => [r.section, r.offence, r.punishment, r.cognizable, r.bailable, r.court]))};\n`
    + '// Section 359 BNSS compounding tables: [part (victim | court), BNS sections, person who may compound]\n'
    + `export const BNSS_COMPOUNDING: [string, string[], string][] = ${JSON.stringify(COMPOUNDING.map((r) => [r.part, r.sections, r.by]))};\n`);

  // Bare Acts landing, grouped by area of law.
  const groups = [
    ['New criminal laws (from 1 July 2024)', (a) => FIRST.includes(a.id)],
    ['Civil, commercial and procedure', (a) => !FIRST.includes(a.id) && a.status !== 'repealed' && !/family|safety|women/i.test(a.area)],
    ['Family, women and children', (a) => !FIRST.includes(a.id) && a.status !== 'repealed' && /family|safety|women/i.test(a.area)],
    ['Repealed laws (for reference)', (a) => a.status === 'repealed'],
  ];
  const card = (a) => `<a class="act" href="/acts/${a.id}/"><b>${esc(a.short)}</b><span>${esc(a.title)}</span><small>${a.sections.length} sections</small></a>`;
  const body = `<main>
<p class="eyebrow">Bare Acts</p>
<h1>India's central Acts, section by section</h1>
<p class="lede">Read ${acts.length} central Acts as clear text, one section per page: the new criminal laws (BNS, BNSS, BSA), the Companies Act, CPC, Contract Act, IBC, IT Act and more, with old-law equivalents where they exist.</p>
<h2 class="group">Old law to new law</h2><div class="acts">${CORRESPONDENCE.map((t) => `<a class="act" href="/acts/${CONVERTERS[t.old_act]}/"><b>${esc(OLD_SHORT[t.old_act])} → ${esc(NEW_SHORT[t.new_act])}</b><span>Find the ${esc(NEW_SHORT[t.new_act])} section for any ${esc(OLD_SHORT[t.old_act])} section</span><small>Converter</small></a>`).join('')}</div>
${groups.map(([name, test]) => { const list = acts.filter(test); return list.length ? `<h2 class="group">${esc(name)}</h2><div class="acts">${list.map(card).join('')}</div>` : ''; }).join('\n')}
${cta({ id: 'bns', short: 'Acts' }, '')}
</main>`;
  writeFileSync(join(OUT, 'index.html'), page({
    title: 'Bare Acts of India section by section — BNS, BNSS, BSA, CPC, IPC and more | VidhiSangh',
    description: `Read ${acts.length} central Acts of India section by section, free: BNS, BNSS, BSA, Companies Act, CPC, Contract Act, IBC, IT Act, Arbitration Act and more.`,
    canonical: `${SITE}/acts/`,
    body,
    jsonLd: { '@context': 'https://schema.org', ...breadcrumbs([['Bare Acts', '/acts/']]) },
  }));
  urls.unshift(['/acts/', 'monthly', '0.9']);

  // Sitemap: the app's public pages, then every act page.
  const fixed = [['/', 'weekly', '1.0'], ['/auth/register', 'monthly', '0.8'], ['/auth/login', 'monthly', '0.5'], ['/help', 'monthly', '0.6'], ['/about', 'yearly', '0.5'], ['/trust', 'monthly', '0.4'], ['/privacy', 'yearly', '0.3'], ['/terms', 'yearly', '0.3']];
  const xml = [...fixed, ...urls].map(([u, f, p]) => `  <url><loc>${SITE}${u}</loc><changefreq>${f}</changefreq><priority>${p}</priority></url>`).join('\n');
  writeFileSync(join(ROOT, 'public/sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${xml}\n</urlset>\n`);
  console.log(`acts pages: ${urls.length}; sitemap urls: ${fixed.length + urls.length}`);
}

build();

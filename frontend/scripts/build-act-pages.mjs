// Generates public, indexable bare-act pages from content/acts/*.json
// (extracted once by scripts/act_sections.py) into public/acts/, and rewrites
// public/sitemap.xml. Plain static HTML: fast, crawlable, no app bootstrap.
//
//   node scripts/build-act-pages.mjs        (from frontend/, before `ng build`)
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

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
// nginx caches .css for a year, so the link carries a content fingerprint.
const CSS = readFileSync(join(ROOT, 'scripts/acts.css'), 'utf8');
const CSS_URL = `/acts/acts.css?v=${createHash('sha256').update(CSS).digest('hex').slice(0, 10)}`;

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const base = (section) => section.toUpperCase().replace(/^SECTION\s*/, '').replace(/[\s(–-].*$/, '');

/** Old-law <-> new-law equivalents curated in the app (section-intelligence.ts),
 *  keyed both ways: 'bns:103' -> IPC 302, and 'ipc:302' -> BNS 103. */
function crossReferences() {
  const src = readFileSync(join(ROOT, 'src/app/features/knowledge/data/section-intelligence.ts'), 'utf8');
  const refs = {};
  const row = /\{ actId: '(\w+)', section: '([^']+)', correspondingActId: '(\w+)', correspondingSection: '([^']+)', subject: '([^']+)'(?:, note: '([^']+)')? \}/g;
  for (const m of src.matchAll(row)) {
    const [, oldAct, oldSection, act, section, subject, note] = m;
    (refs[`${act}:${base(section)}`] ??= []).push({ oldAct, oldSection, section, subject, note });
    (refs[`${oldAct}:${base(oldSection)}`] ??= []).push({ newAct: act, newSection: section, oldSection, subject, note });
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
  <nav><a class="join" href="${JOIN}">Join now</a><a class="signin" href="/auth/login">Sign in</a></nav>
</header>
${body}
<footer>
  <p><a href="/acts/">Bare Acts</a> · <a href="/">VidhiSangh</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></p>
  <p>VidhiSangh is developed and managed by <a href="/about">Simson Softwares Private Limited</a>. WhatsApp: <a href="https://wa.me/917341100692" rel="noopener">+91 73411 00692</a></p>
  <p>Text reproduced from the official publication for reference. Check the official source and later amendments before relying on it.</p>
</footer>
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

function cta(act, number) {
  const reader = `/app/knowledge/reader?act=${act.id}${number ? `&section=${encodeURIComponent(number)}` : ''}`;
  return `<aside class="cta">
  <div><strong>Read, search and save the full ${esc(act.short)} free</strong>
  <span>Plus 5.9 million Supreme Court and High Court judgments, and a professional network for India's legal fraternity.</span></div>
  <div class="cta-buttons"><a class="primary" href="${JOIN}">Join VidhiSangh free</a><a class="ghost" href="${reader}">Open in the app</a></div>
</aside>`;
}

function build() {
  const refs = crossReferences();
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, 'acts.css'), CSS);
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
      const old = links.filter((r) => r.oldAct);
      const now = links.filter((r) => r.newAct);
      const first = sec.paragraphs.join(' ').replace(/^\d+[A-Z]*\.\s*/, '');
      const description = `Section ${sec.number}, ${act.title} (${act.short})${sec.heading ? `: ${sec.heading}` : ''}. ${first}`.slice(0, 158).replace(/\s+\S*$/, '') + '…';
      const title = sec.heading
        ? `Section ${sec.number} ${act.short} — ${sec.heading} | ${act.title}`
        : `Section ${sec.number}, ${act.title} (${act.short}) | VidhiSangh`;
      const [chapterNo, chapterName = ''] = sec.chapter.split(' — ');
      const body = `<main>
<nav class="crumbs" aria-label="Breadcrumb"><a href="/acts/">Bare Acts</a> › <a href="${actUrl}">${esc(act.short)}</a>${chapterNo ? ` › <span>${esc(chapterNo.replace('CHAPTER', 'Chapter').replace('PART', 'Part'))}</span>` : ''}</nav>
<p class="eyebrow">${esc(act.title)}</p>
<h1>${esc(label(sec))}</h1>
${repealed}
${chapterNo ? `<p class="chapter">${esc(chapterNo.replace('CHAPTER', 'Chapter').replace('PART', 'Part'))}${chapterName ? ` — ${esc(chapterName)}` : ''}</p>` : ''}
<article class="text">
${paragraphs(sec.paragraphs)}
</article>
${old.map((r) => `<section class="old-law"><h2>Old law equivalent</h2><p>${esc(OLD_ACTS[r.oldAct] ?? r.oldAct)}, section ${esc(r.oldSection)} — ${esc(r.subject)}${r.section !== sec.number ? ` (now ${esc(act.short)} ${esc(r.section)})` : ''}.</p>${r.note ? `<p class="small">${esc(r.note)}</p>` : ''}</section>`).join('\n')}
${now.map((r) => `<section class="old-law"><h2>Now in the new law</h2><p><a href="/acts/${r.newAct}/section-${base(r.newSection).toLowerCase()}/">${esc(r.newAct.toUpperCase())} section ${esc(r.newSection)}</a> — ${esc(r.subject)}.</p>${r.note ? `<p class="small">${esc(r.note)}</p>` : ''}</section>`).join('\n')}
${cta(act, sec.number)}
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
<nav class="crumbs" aria-label="Breadcrumb"><a href="/acts/">Bare Acts</a> › <span>${esc(act.short)}</span></nav>
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

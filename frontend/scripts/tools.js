// Calculators on vidhisangh.com/tools/ (copied to /tools/tools.js by
// scripts/build-act-pages.mjs). Dates are typed dd/mm/yyyy.
(() => {
  const WORDS = { one: 1, two: 2, three: 3, six: 6, ten: 10, twelve: 12, thirty: 30, sixty: 60, ninety: 90 };
  const DAY = 86400000;
  const COVID_FROM = Date.UTC(2020, 2, 15), COVID_TO = Date.UTC(2022, 1, 28);
  const pad = (n) => String(n).padStart(2, '0');
  const fmt = (t) => { const d = new Date(t); return `${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getUTCDay()]} ${pad(d.getUTCDate())}/${pad(d.getUTCMonth() + 1)}/${d.getUTCFullYear()}`; };
  function parseDate(s) {
    const m = String(s || '').trim().match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
    if (!m) return null;
    const t = Date.UTC(+m[3], +m[2] - 1, +m[1]);
    const d = new Date(t);
    return d.getUTCDate() === +m[1] && d.getUTCMonth() === +m[2] - 1 ? t : null;
  }
  function parsePeriods(text) {
    return [...String(text).matchAll(/(One|Two|Three|Six|Ten|Twelve|Thirty|Sixty|Ninety)\s+(years?|days|months?)/gi)]
      .map((m) => ({ n: WORDS[m[1].toLowerCase()], unit: m[2].toLowerCase().replace(/s$/, ''), label: `${m[1]} ${m[2]}` }));
  }
  /** Section 12(1): the first day is excluded, so the period ends on the same date N units later. */
  function addPeriod(t, { n, unit }) {
    const d = new Date(t);
    if (unit === 'day') return t + n * DAY;
    const months = unit === 'year' ? n * 12 : n;
    const y = d.getUTCFullYear(), m = d.getUTCMonth() + months, day = d.getUTCDate();
    const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
    return Date.UTC(y, m, Math.min(day, last));
  }
  const $ = (root, sel) => root.querySelector(sel);

  const forms = (sel) => (typeof document === 'undefined' ? [] : document.querySelectorAll(sel));
  for (const form of forms('form[data-tool="limitation"]')) {
    const data = JSON.parse(document.getElementById('limitation-data').textContent);
    const article = $(form, '[name=article]'), clause = $(form, '[name=clause]'), clauseRow = $(form, '.clause-row');
    const customRow = $(form, '.custom-row'), out = $(form.parentElement, '.tool-result'), info = $(form, '.article-info');
    const current = () => data.find((a) => String(a.article) === article.value);
    const refresh = () => {
      const a = current();
      customRow.hidden = !!a;
      const periods = a ? parsePeriods(a.period) : [];
      clauseRow.hidden = periods.length < 2;
      clause.innerHTML = periods.map((p, i) => `<option value="${i}">(${String.fromCharCode(97 + i)}) ${p.label}</option>`).join('');
      info.innerHTML = a ? `<b>Article ${a.article}.</b> ${escapeHtml(a.description)}<br><span>Period: ${escapeHtml(a.period)} Runs from: ${escapeHtml(a.from)}</span>` : '';
    };
    article.addEventListener('change', refresh);
    refresh();
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const start = parseDate($(form, '[name=start]').value);
      if (start === null) { out.innerHTML = '<p class="error">Enter the date as dd/mm/yyyy.</p>'; return; }
      const a = current();
      let period;
      if (a) period = parsePeriods(a.period)[+clause.value || 0];
      else {
        const n = parseInt($(form, '[name=n]').value, 10);
        if (!(n > 0)) { out.innerHTML = '<p class="error">Enter the period.</p>'; return; }
        period = { n, unit: $(form, '[name=unit]').value, label: `${n} ${$(form, '[name=unit]').value}(s)` };
      }
      const excluded = Math.max(0, parseInt($(form, '[name=excluded]').value || '0', 10) || 0);
      const end = addPeriod(start, period) + excluded * DAY;
      const notes = [];
      if (new Date(end).getUTCDay() === 0) notes.push(`That day is a Sunday. If the court is closed on the last day, the suit, appeal or application may be filed on the day it reopens (Section 4), e.g. ${fmt(end + DAY)}.`);
      else notes.push('If the court is closed on that day, it may be filed on the day the court reopens (Section 4).');
      if (excluded) notes.push(`Includes ${excluded} day(s) excluded for obtaining certified copies (Section 12(2)–(3)).`);
      if (start <= COVID_TO && end >= COVID_FROM) notes.push('This period overlaps 15/03/2020–28/02/2022, which the Supreme Court excluded from limitation (In Re: Cognizance for Extension of Limitation, order of 10/01/2022). Recalculate with that exclusion.');
      if (a && a.division && !/Suits/.test(a.division)) notes.push('Appeals and applications may be admitted after the period if there was sufficient cause (Section 5); suits may not.');
      out.innerHTML = `<p class="answer">Last date: <strong>${fmt(end)}</strong></p><p class="small">${escapeHtml(period.label)} from ${fmt(start)}, the first day excluded (Section 12(1)).</p><ul class="small">${notes.map((n) => `<li>${escapeHtml(n)}</li>`).join('')}</ul>`;
    });
  }

  for (const form of forms('form[data-tool="default-bail"]')) {
    const out = $(form.parentElement, '.tool-result');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const remand = parseDate($(form, '[name=remand]').value);
      if (remand === null) { out.innerHTML = '<p class="error">Enter the date as dd/mm/yyyy.</p>'; return; }
      const days = +$(form, '[name=offence]:checked').value;
      const last = remand + (days - 1) * DAY;
      out.innerHTML = `<p class="answer">Charge sheet due by: <strong>${fmt(last)}</strong> (day ${days})</p>
<p>If no charge sheet is filed by then, the right to default bail arises on <strong>${fmt(last + DAY)}</strong>, provided the accused applies and is prepared to furnish bail, before the charge sheet is filed.</p>
<p class="small">${days} days under Section 187(3) BNSS (formerly Section 167(2) CrPC), counted from the date of the first remand, that day included (Enforcement Directorate v. Kapil Wadhawan, 2023). Special laws set longer periods (e.g. 180 days under the NDPS Act and UAPA).</p>`;
    });
  }

  /** Interest between two dates: simple, or compounded n times a year (365-day year). */
  function interest(principal, ratePct, from, to, perYear) {
    const days = Math.round((to - from) / DAY);
    const t = days / 365, r = ratePct / 100;
    const total = perYear ? principal * Math.pow(1 + r / perYear, perYear * t) : principal * (1 + r * t);
    return { days, interest: total - principal, total };
  }
  const rupees = (n) => `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  for (const form of forms('form[data-tool="interest"]')) {
    const out = $(form.parentElement, '.tool-result');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const principal = parseFloat(String($(form, '[name=principal]').value).replace(/[,₹\s]/g, ''));
      const rate = parseFloat($(form, '[name=rate]').value);
      const from = parseDate($(form, '[name=from]').value), to = parseDate($(form, '[name=to]').value);
      if (!(principal > 0) || !(rate >= 0)) { out.innerHTML = '<p class="error">Enter the amount and the rate.</p>'; return; }
      if (from === null || to === null) { out.innerHTML = '<p class="error">Enter both dates as dd/mm/yyyy.</p>'; return; }
      if (to <= from) { out.innerHTML = '<p class="error">The end date must be after the start date.</p>'; return; }
      const perYear = +$(form, '[name=compound]').value;
      const r = interest(principal, rate, from, to, perYear);
      out.innerHTML = `<p class="answer">Interest: <strong>${rupees(r.interest)}</strong></p>
<p>Total with principal: <strong>${rupees(r.total)}</strong></p>
<p class="small">${rupees(principal)} at ${rate}% a year, ${perYear ? `compounded ${({ 1: 'yearly', 4: 'quarterly', 12: 'monthly' })[perYear]}` : 'simple interest'}, for ${r.days} days (${fmt(from)} to ${fmt(to)}), 365-day year.</p>`;
    });
  }

  function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }

  // ── Offence screener (BNSS First Schedule) ─────────────────────────
  const TERM_WORDS = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, ten: 10, fourteen: 14, twenty: 20 };
  /** What the punishment column allows at most: death, life, a term in years, or fine only. */
  function maxTerm(punishment) {
    const p = String(punishment).toLowerCase();
    const death = /\bdeath\b/.test(p);
    const life = /imprisonment for life|remainder of (that|his) person's natural life|for life/.test(p);
    let years = null;
    for (const m of p.matchAll(/(\d+|one|two|three|four|five|six|seven|ten|fourteen|twenty)\s+years?/g)) years = Math.max(years ?? 0, TERM_WORDS[m[1]] ?? +m[1]);
    for (const m of p.matchAll(/(\d+|one|two|three|six)\s+months?/g)) years = Math.max(years ?? 0, (TERM_WORDS[m[1]] ?? +m[1]) / 12);
    const fineOnly = !death && !life && years === null && /fine/.test(p);
    return { death, life, years, fineOnly };
  }
  /** Section 187(3) BNSS: 90 days where the offence is punishable with death, life, or ten years or more; else 60. */
  function defaultBailDays(term) { return term.death || term.life || (term.years !== null && term.years >= 10) ? 90 : 60; }
  /** Section 35 BNSS: for a cognizable offence punishable up to 7 years the police first issue a notice to appear
   *  (35(3)) and arrest only for reasons recorded (35(1)(b)); beyond 7 years, arrest without warrant. */
  function arrestRegime(term, cognizable) {
    if (cognizable !== 'cognizable') return cognizable === 'non_cognizable' ? 'warrant' : 'depends';
    return term.death || term.life || (term.years !== null && term.years > 7) ? 'arrest' : 'notice';
  }
  /** Section 482(4) BNSS: no anticipatory bail for offences under section 65 or 70(2) BNS. */
  function anticipatoryBail(section) { return !/^(65\b|70\(2\))/.test(String(section)); }
  const base = (s) => String(s).replace(/\s+/g, '').replace(/\(.*$/, '').toUpperCase();
  /** Rows of the Schedule for a query: a BNS section, "IPC 420", or words from the offence. */
  function screen(data, query) {
    const q = String(query || '').trim().replace(/^(section|sec\.?|s\.)\s*/i, '');
    if (!q) return { rows: [], via: null };
    const ipc = q.match(/^(?:ipc\s*)?(\d+[A-Z]{0,2}(?:\(\w+\))?)\s*(?:ipc|of the ipc|indian penal code)$/i) || q.match(/^ipc\s*(\d+[A-Z]{0,2}(?:\(\w+\))?)$/i);
    if (ipc) {
      const news = (data.ipc_to_bns || {})[ipc[1].toUpperCase()] || (data.ipc_to_bns || {})[ipc[1]] || [];
      // "318(4)" names one limb; "85" means every entry of that section.
      const exact = new Set(news.filter((s) => s.includes('(')).map((s) => s.replace(/\s+/g, '').toUpperCase()));
      const whole = new Set(news.filter((s) => !s.includes('(')).map(base));
      const rows = data.part_i.filter((r) => exact.has(r.section.replace(/\s+/g, '').toUpperCase()) || whole.has(base(r.section)));
      return { rows, via: { ipc: ipc[1].toUpperCase(), bns: news } };
    }
    const sec = q.match(/^(?:bns\s*)?(\d{1,3})(\(\w{1,3}\))?\s*(?:bns)?$/i);
    if (sec) {
      const exact = data.part_i.filter((r) => r.section.replace(/\s+/g, '') === `${sec[1]}${sec[2] || ''}`);
      return { rows: exact.length && sec[2] ? exact : data.part_i.filter((r) => base(r.section) === sec[1]), via: null };
    }
    const terms = q.toLowerCase().split(/\s+/).filter((t) => t.length > 2);
    return { rows: terms.length ? data.part_i.filter((r) => terms.every((t) => r.offence.toLowerCase().includes(t))).slice(0, 25) : [], via: null };
  }
  const FLAG_LABEL = { cognizable: 'Cognizable', non_cognizable: 'Non-cognizable', bailable: 'Bailable', non_bailable: 'Non-bailable', according: 'According as the offence abetted / attempted' };
  function renderRow(r) {
    const term = maxTerm(r.punishment);
    const days = defaultBailDays(term);
    const regime = arrestRegime(term, r.cognizable);
    const notes = [];
    if (r.cognizable === 'cognizable' || r.cognizable === 'according') notes.push(regime === 'arrest'
      ? 'Arrest without warrant: the punishment exceeds 7 years, so Section 35(3) BNSS (notice to appear instead of arrest) does not apply.'
      : regime === 'notice' ? 'Punishable up to 7 years: under Section 35(3) BNSS the police issue a notice to appear and arrest only for reasons recorded in writing (Section 35(1)(b)); Arnesh Kumar guidelines apply.'
      : 'Cognizability follows the principal offence, so check that offence for the arrest regime.');
    else notes.push('Non-cognizable: no arrest without a warrant or an order of a Magistrate (Sections 2(1)(o) and 174 BNSS).');
    notes.push(term.fineOnly ? 'Punishable with fine only.' : `Default bail: ${days} days from the first remand under Section 187(3) BNSS (${days === 90 ? 'death, life or 10 years or more' : 'other offences'}).`);
    if (!anticipatoryBail(r.section)) notes.push('Anticipatory bail is not available for this offence (Section 482(4) BNSS).');
    if (r.bailable === 'bailable') notes.push('Bailable: bail is a right under Section 478 BNSS; the police or the court must release on bail.');
    const sectionUrl = `/acts/bns/section-${base(r.section).toLowerCase()}/`;
    return `<article class="offence">
<h3><a href="${sectionUrl}">Section ${escapeHtml(r.section)} BNS</a> — ${escapeHtml(r.offence)}</h3>
<dl><div><dt>Punishment</dt><dd>${escapeHtml(r.punishment)}</dd></div>
<div><dt>Cognizable?</dt><dd><strong class="${r.cognizable}">${escapeHtml(FLAG_LABEL[r.cognizable] || r.cognizable_text)}</strong>${r.cognizable === 'according' ? ` <small>${escapeHtml(r.cognizable_text)}</small>` : ''}</dd></div>
<div><dt>Bailable?</dt><dd><strong class="${r.bailable}">${escapeHtml(FLAG_LABEL[r.bailable] || r.bailable_text)}</strong>${r.bailable === 'according' ? ` <small>${escapeHtml(r.bailable_text)}</small>` : ''}</dd></div>
<div><dt>Triable by</dt><dd>${escapeHtml(r.court)}</dd></div></dl>
<ul class="small">${notes.map((n) => `<li>${escapeHtml(n)}</li>`).join('')}</ul>
</article>`;
  }
  for (const form of forms('form[data-tool="offence"]')) {
    const out = $(form.parentElement, '.tool-result');
    let data = null;
    const load = () => data ? Promise.resolve(data) : fetch(form.dataset.src).then((r) => r.json()).then((d) => (data = d));
    const run = async () => {
      const q = $(form, '[name=q]').value;
      if (!q.trim()) { out.innerHTML = ''; return; }
      out.innerHTML = '<p class="small">Looking up the Schedule…</p>';
      try {
        const d = await load();
        const { rows, via } = screen(d, q);
        const lead = via ? `<p class="answer">IPC ${escapeHtml(via.ipc)} is now ${via.bns.length ? via.bns.map((s) => `<strong>BNS ${escapeHtml(s)}</strong>`).join(', ') : 'not carried into the BNS'}.</p>` : '';
        out.innerHTML = rows.length ? lead + rows.map(renderRow).join('')
          : `${lead}<p class="error">No entry in the First Schedule matches “${escapeHtml(q)}”. Sections 1–48 of the BNS define terms and general exceptions and carry no offence; try the section number of the offence (e.g. 303(2)), “IPC 420”, or a word from the offence (e.g. “cheating”).</p>`;
      } catch { out.innerHTML = '<p class="error">The Schedule could not be loaded. Please try again.</p>'; }
    };
    form.addEventListener('submit', (e) => { e.preventDefault(); void run(); });
    const initial = new URLSearchParams(location.search).get('q');
    if (initial) { $(form, '[name=q]').value = initial; void run(); }
  }
  if (typeof module !== 'undefined') module.exports = { parseDate, parsePeriods, addPeriod, interest, maxTerm, defaultBailDays, arrestRegime, anticipatoryBail, screen };
})();

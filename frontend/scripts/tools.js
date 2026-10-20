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

  function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }
  if (typeof module !== 'undefined') module.exports = { parseDate, parsePeriods, addPeriod };
})();

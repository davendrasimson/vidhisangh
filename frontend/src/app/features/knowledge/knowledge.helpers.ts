import { ActGuide } from './data/acts';

export function matchesAct(act: ActGuide, query: string): boolean {
  const text = [act.title, act.short, act.area, act.status, act.statusNote, act.summary, ...act.usefulFor,
    ...act.provisions.map((p) => `${p.reference} ${p.meaning}`)].join(' ').toLowerCase();
  return query.toLowerCase().trim().split(/\s+/).every((word) => text.includes(word));
}

export interface ActMatch {
  act: ActGuide;
  score: number;
  reason: string;
}

const SCENARIO_HINTS: Record<string, { terms: string[]; reason: string }> = {
  cheque: { terms: ['cheque', 'check', 'bounce', 'dishonour', 'dishonor'], reason: 'This guide covers cheque dishonour and the notice and filing steps that may follow.' },
  consumer: { terms: ['refund', 'seller', 'product', 'service', 'consumer', 'customer', 'defective', 'online shopping'], reason: 'This may cover defective goods, deficient services or an unfair trade practice.' },
  rera: { terms: ['flat', 'builder', 'apartment', 'real estate', 'possession', 'construction', 'homebuyer', 'property delay'], reason: 'This may apply to a covered real-estate project or a delayed home purchase.' },
  contract: { terms: ['contract', 'agreement', 'promise', 'breach', 'invoice', 'unpaid', 'payment', 'work'], reason: 'This may help assess whether an agreement is enforceable and what follows a breach.' },
  bns: { terms: ['stolen', 'theft', 'threat', 'assault', 'cheating', 'fraud', 'crime', 'criminal', 'police'], reason: 'This guide explains criminal offences; the exact facts and date determine the applicable provision.' },
  bnss: { terms: ['fir', 'police complaint', 'arrest', 'bail', 'investigation', 'criminal case'], reason: 'This guide explains criminal procedure such as reporting, arrest and bail.' },
  bsa: { terms: ['evidence', 'screenshot', 'whatsapp', 'email', 'recording', 'proof', 'digital'], reason: 'This may help with proving electronic records and other evidence.' },
  dv: { terms: ['domestic violence', 'husband', 'wife', 'abuse', 'shared home', 'maintenance', 'dowry'], reason: 'This may provide protection, residence or monetary relief for domestic violence.' },
  cpc: { terms: ['civil suit', 'summons', 'court notice', 'money recovery', 'property dispute', 'plaint'], reason: 'This explains the procedure for a civil claim or court summons.' },
  limitation: { terms: ['deadline', 'late', 'limitation', 'time limit', 'old debt', 'delay'], reason: 'Limitation periods may affect whether a proceeding can still be started.' },
  companies: { terms: ['company', 'director', 'shareholder', 'incorporation', 'annual filing', 'mca'], reason: 'This covers company formation, governance and director responsibilities.' },
  it: { terms: ['cyber', 'online fraud', 'hacked', 'password', 'identity theft', 'computer', 'digital fraud'], reason: 'This may cover specified misuse of computer systems or digital identity.' },
  'legal-aid': { terms: ['free lawyer', 'cannot afford', 'legal aid', 'lok adalat'], reason: 'This explains routes to legal services for eligible people.' },
};

export function rankActs(query: string, acts: ActGuide[]): ActMatch[] {
  const normalized = query.toLowerCase().trim();
  if (!normalized) return [];
  const words = normalized.split(/[^a-z0-9]+/).filter((word) => word.length > 2);
  return acts.map((act) => {
    const text = [act.title, act.short, act.area, act.summary, act.example, ...act.usefulFor,
      ...act.provisions.map((p) => `${p.reference} ${p.meaning}`)].join(' ').toLowerCase();
    let score = words.reduce((total, word) => total + (text.includes(word) ? 1 : 0), 0);
    let reason = 'This guide contains related terms, but a lawyer should confirm whether it applies.';
    const hint = SCENARIO_HINTS[act.id];
    if (hint) {
      const hits = hint.terms.filter((term) => normalized.includes(term));
      score += hits.length * 3;
      if (hits.length) reason = hint.reason;
    }
    return { act, score, reason };
  }).filter((match) => match.score > 0).sort((a, b) => b.score - a.score || a.act.title.localeCompare(b.act.title));
}

export function placeholders(body: string): string[] {
  return [...new Set([...body.matchAll(/\{\{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*\}\}/g)].map((m) => m[1]))];
}

export function fillTemplate(body: string, values: Record<string, string>): string {
  return body.replace(/\{\{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*\}\}/g, (match, key: string) => values[key]?.trim() || match);
}

export function checklistLines(body: string): string[] {
  return body.split('\n').map((line) => line.trim()).filter((line) => /^(?:[-*]\s+|\d+[.)]\s+|\[[ xX]\]\s+)/.test(line))
    .map((line) => line.replace(/^(?:[-*]\s+|\d+[.)]\s+)?(?:\[[ xX]\]\s*)?/, '').trim()).filter(Boolean);
}

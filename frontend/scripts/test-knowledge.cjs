const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');
require.extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  module._compile(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
};
const { ACTS } = require('../src/app/features/knowledge/data/acts.ts');
const { matchesAct, rankActs, placeholders, fillTemplate, checklistLines } = require('../src/app/features/knowledge/knowledge.helpers.ts');
assert.equal(new Set(ACTS.map(a => a.id)).size, ACTS.length);
for (const act of ACTS) {
  assert.match(new URL(act.source).hostname, /(^|\.)indiacode\.nic\.in$/);
  assert.ok(act.summary && act.note && act.example && act.provisions.length && act.prepare.length);
  for (const id of act.related) assert.ok(ACTS.some(a => a.id === id), `${act.id}: missing related guide ${id}`);
}
for (const id of ['ipc', 'crpc', 'evidence']) assert.equal(ACTS.find(a => a.id === id).legacy, true);
assert.deepEqual(ACTS.filter(a => matchesAct(a, ' cheque BOUNCE ')).map(a => a.id), ['cheque']);
assert.ok(matchesAct(ACTS.find(a => a.id === 'bns'), 'BNS 303'));
assert.ok(matchesAct(ACTS.find(a => a.id === 'legal-aid'), 'free lawyer'));
const flatResults = rankActs('I paid a builder for a flat and possession is late, please refund me', ACTS);
assert.deepEqual(flatResults.slice(0, 3).map(({act}) => act.id), ['rera', 'consumer', 'limitation']);
assert.ok(flatResults.some(({act}) => act.id === 'contract'));
assert.ok(flatResults.find(({act}) => act.id === 'rera').reason.includes('real-estate'));
assert.ok(rankActs('my cheque bounced', ACTS)[0].act.id === 'cheque');
assert.equal(ACTS.filter(a => matchesAct(a, 'unmatchedterm')).length, 0);
assert.deepEqual(placeholders('{{client_name}} / {{ client_name }} / {{matter_number}}'), ['client_name', 'matter_number']);
assert.equal(fillTemplate('{{name}} / {{missing}}', {name: '$& <b>A</b>'}), '$& <b>A</b> / {{missing}}');
assert.deepEqual(checklistLines('Preparation\n- [ ] Collect records\n2. Check dates\n* Review draft\n[x] Confirm client\n\nNotes'), ['Collect records', 'Check dates', 'Review draft', 'Confirm client']);
if (process.argv.includes('--export')) fs.writeFileSync('/tmp/knowledge-acts.json', JSON.stringify(ACTS, null, 2));
console.log(`Passed: ${ACTS.length} Act guides, source/related-link integrity, legacy labels, search, placeholders and checklist parsing.`);

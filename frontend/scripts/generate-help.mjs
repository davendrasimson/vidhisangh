// The in-app articles are also published as a printable, offline user guide.
import { writeFileSync } from 'node:fs';
import { HELP_TOPICS } from '../src/app/features/help/help-content.ts';
const lines = [
  '# VidhiSangh user guide', '',
  'Use **Help** in the top bar for the current page. The **light bulb** opens a short tip about what else you can do there. Both popups can be closed with Escape and leave the current form in place.', '',
  'Open **Help & feature tour** in the navigation to search all articles or take the feature tour. The tour has Back, Next, Close and Finish controls and can be replayed at any time. It explains features without creating records or navigating away from your work.', '',
  'Feature availability depends on your role, subscription and configured services. Ask your organisation administrator if a described action is unavailable. For account assistance, open **Support & grievance** from the top bar or account menu.', '',
  '## Explore the product', '',
  ...HELP_TOPICS.filter(t => t.featured).map(t => `- [${t.title}](#${t.id}): ${t.summary}`), '',
  ...HELP_TOPICS.flatMap(t => [
    `<a id="${t.id}"></a>`, `## ${t.title}`, '', t.summary, '',
    ...t.steps.map((step, i) => `${i + 1}. ${step}`), '', `**Tip:** ${t.tip}`, '',
  ]),
];
writeFileSync(new URL('../../docs/help/user-guide.md', import.meta.url), lines.join('\n'));

export type ApplicabilityTone = 'current' | 'historical' | 'warning' | 'unavailable';

export interface LawTimelineEvent {
  date: string;
  label: string;
  detail: string;
  source: string;
  sourceLabel: string;
}

export interface LawVersionProfile {
  actId: string;
  commencedOn: string;
  transitionOn: string;
  counterpartActId: string;
  transitionKind: 'substantive' | 'procedure' | 'evidence';
  savingSection: string;
  savingRule: string;
  factToCheck: string;
  notification: string;
  timeline: LawTimelineEvent[];
  generation: 'old' | 'new';
}

export interface LawApplicability {
  tone: ApplicabilityTone;
  label: string;
  headline: string;
  detail: string;
  factToCheck?: string;
  source?: string;
  sourceLabel?: string;
  counterpartActId?: string;
}

const BNS_NOTIFICATION = 'https://www.mha.gov.in/sites/default/files/BhartiyaNyayaSanhita_24022024.pdf';
const BNSS_NOTIFICATION = 'https://www.mha.gov.in/sites/default/files/BharatiyaNagarikSurakshaSanhita_24022024.pdf';
const BSA_NOTIFICATION = 'https://www.mha.gov.in/sites/default/files/BharatiyaSakshyaAdhiniyam_24022024.pdf';
const BNS_ACT = 'https://www.indiacode.nic.in/bitstream/123456789/20062/1/a2023-45.pdf';
const BNSS_ACT = 'https://www.indiacode.nic.in/bitstream/123456789/21920/1/the_bharatiya_nagarik_suraksha_sanhita%2C_2023.pdf';
const BSA_ACT = 'https://www.indiacode.nic.in/bitstream/123456789/20063/1/a2023-47.pdf';

const COMMON_ASSENT: LawTimelineEvent = {
  date: '2023-12-25',
  label: 'New criminal laws enacted',
  detail: 'The three replacement enactments received assent and were published as Acts 45, 46 and 47 of 2023.',
  source: BNS_ACT,
  sourceLabel: 'Published Act',
};

function commencementEvent(notification: string, exception = ''): LawTimelineEvent {
  return {
    date: '2024-02-23',
    label: 'Commencement notified',
    detail: `The Central Government appointed 1 July 2024 as the commencement date${exception}.`,
    source: notification,
    sourceLabel: 'Gazette notification',
  };
}

function transitionEvent(detail: string, source: string, section: string): LawTimelineEvent {
  return {
    date: '2024-07-01',
    label: 'New regime commenced',
    detail,
    source,
    sourceLabel: `Repeal and savings · Section ${section}`,
  };
}

const PROFILES: Record<string, LawVersionProfile> = {
  bns: {
    actId: 'bns', commencedOn: '2024-07-01', transitionOn: '2024-07-01', counterpartActId: 'ipc',
    transitionKind: 'substantive', savingSection: '358', generation: 'new', notification: BNS_NOTIFICATION,
    savingRule: 'The IPC was repealed, but previous operation, accrued liabilities, penalties, investigations and proceedings are preserved by BNS section 358.',
    factToCheck: 'For an offence, confirm the date of the alleged conduct. Conduct before 1 July 2024 may continue under the IPC through the savings clause.',
    timeline: [COMMON_ASSENT, commencementEvent(BNS_NOTIFICATION, ', except BNS section 106(2)'), transitionEvent('BNS commenced and repealed the IPC, subject to the detailed savings in section 358. Section 106(2) was excluded from this commencement.', BNS_ACT, '358')],
  },
  ipc: {
    actId: 'ipc', commencedOn: '1862-01-01', transitionOn: '2024-07-01', counterpartActId: 'bns',
    transitionKind: 'substantive', savingSection: '358 BNS', generation: 'old', notification: BNS_NOTIFICATION,
    savingRule: 'BNS section 358 preserves the IPC for its previous operation, offences already committed, accrued liabilities, penalties, investigations and proceedings.',
    factToCheck: 'Confirm when the alleged offence occurred. The event date, rather than the filing date alone, can determine whether IPC or BNS provisions apply.',
    timeline: [COMMON_ASSENT, commencementEvent(BNS_NOTIFICATION, ', except BNS section 106(2)'), transitionEvent('BNS commenced and repealed the IPC, while section 358 preserved earlier operation and proceedings.', BNS_ACT, '358')],
  },
  bnss: {
    actId: 'bnss', commencedOn: '2024-07-01', transitionOn: '2024-07-01', counterpartActId: 'crpc',
    transitionKind: 'procedure', savingSection: '531', generation: 'new', notification: BNSS_NOTIFICATION,
    savingRule: 'BNSS section 531 directs appeals, applications, trials, inquiries and investigations already pending immediately before commencement to continue under the CrPC.',
    factToCheck: 'Confirm whether the appeal, application, trial, inquiry or investigation was pending immediately before 1 July 2024.',
    timeline: [COMMON_ASSENT, commencementEvent(BNSS_NOTIFICATION, ', except the First Schedule entry relating to BNS section 106(2)'), transitionEvent('BNSS commenced and repealed the CrPC, with pending proceedings preserved under section 531.', BNSS_ACT, '531')],
  },
  crpc: {
    actId: 'crpc', commencedOn: '1974-04-01', transitionOn: '2024-07-01', counterpartActId: 'bnss',
    transitionKind: 'procedure', savingSection: '531 BNSS', generation: 'old', notification: BNSS_NOTIFICATION,
    savingRule: 'BNSS section 531 preserves the CrPC for appeals, applications, trials, inquiries and investigations pending immediately before 1 July 2024.',
    factToCheck: 'Confirm whether the relevant proceeding or investigation was already pending immediately before 1 July 2024. The date of the underlying offence alone may not answer this procedural question.',
    timeline: [COMMON_ASSENT, commencementEvent(BNSS_NOTIFICATION, ', except the First Schedule entry relating to BNS section 106(2)'), transitionEvent('BNSS commenced and repealed the CrPC, but preserved pending matters under section 531.', BNSS_ACT, '531')],
  },
  bsa: {
    actId: 'bsa', commencedOn: '2024-07-01', transitionOn: '2024-07-01', counterpartActId: 'evidence',
    transitionKind: 'evidence', savingSection: '170', generation: 'new', notification: BSA_NOTIFICATION,
    savingRule: 'BSA section 170 preserves the Evidence Act for an application, trial, inquiry, investigation, proceeding or appeal pending immediately before commencement.',
    factToCheck: 'Confirm whether the application, trial, inquiry, investigation, proceeding or appeal was pending immediately before 1 July 2024.',
    timeline: [COMMON_ASSENT, commencementEvent(BSA_NOTIFICATION), transitionEvent('BSA commenced and repealed the Evidence Act, with pending matters preserved under section 170.', BSA_ACT, '170')],
  },
  evidence: {
    actId: 'evidence', commencedOn: '1872-09-01', transitionOn: '2024-07-01', counterpartActId: 'bsa',
    transitionKind: 'evidence', savingSection: '170 BSA', generation: 'old', notification: BSA_NOTIFICATION,
    savingRule: 'BSA section 170 preserves the Evidence Act for applications, trials, inquiries, investigations, proceedings and appeals pending immediately before 1 July 2024.',
    factToCheck: 'Confirm whether the proceeding was already pending immediately before 1 July 2024. If it was, the Evidence Act may continue to govern it.',
    timeline: [COMMON_ASSENT, commencementEvent(BSA_NOTIFICATION), transitionEvent('BSA commenced and repealed the Evidence Act, while preserving pending matters under section 170.', BSA_ACT, '170')],
  },
};

export function lawVersionProfile(actId: string): LawVersionProfile | null {
  return PROFILES[actId] ?? null;
}

export function lawApplicability(actId: string, onDate: string, section = ''): LawApplicability {
  const profile = lawVersionProfile(actId);
  if (!profile) {
    return {
      tone: 'unavailable', label: 'Current text only', headline: 'Historical versions are being added',
      detail: 'This Act can be read and searched, but a verified date-specific amendment history is not yet available in VidhiSangh.',
    };
  }

  if (onDate < profile.commencedOn) {
    return {
      tone: 'warning', label: 'Not yet in force', headline: `This Act had not commenced on ${displayDate(onDate)}`,
      detail: `Its verified commencement date is ${displayDate(profile.commencedOn)}. Check the earlier law for the selected date.`,
      source: profile.notification, sourceLabel: 'Official commencement notification', counterpartActId: profile.counterpartActId,
    };
  }

  if (profile.generation === 'new') {
    const isSection106 = actId === 'bns' && /^106(?:\D|$)/i.test(section.trim());
    if (isSection106 && onDate >= profile.transitionOn) {
      return {
        tone: 'warning', label: 'Partly commenced', headline: 'Section 106 needs subsection-level checking',
        detail: 'Section 106(1) commenced on 1 July 2024. Section 106(2) was expressly excluded from S.O. 850(E); do not treat the whole section as uniformly commenced.',
        factToCheck: 'Identify whether the facts engage subsection (1) or subsection (2).', source: profile.notification,
        sourceLabel: 'Official commencement notification', counterpartActId: profile.counterpartActId,
      };
    }
    return {
      tone: 'current', label: 'In force on this date', headline: `Applicable regime from ${displayDate(profile.commencedOn)}`,
      detail: profile.savingRule, factToCheck: profile.factToCheck, source: profile.notification,
      sourceLabel: 'Official commencement notification', counterpartActId: profile.counterpartActId,
    };
  }

  if (onDate < profile.transitionOn) {
    return {
      tone: 'historical', label: 'In force on this date', headline: `The ${actShortName(actId)} was the operative regime`,
      detail: `The replacement regime commenced on ${displayDate(profile.transitionOn)}. Use the text and amendments that were in force on the selected date.`,
      factToCheck: profile.factToCheck, source: profile.notification, sourceLabel: 'Official transition notification',
    };
  }

  return {
    tone: 'historical', label: 'Repealed · savings may apply', headline: 'The earlier law can still govern a saved matter',
    detail: profile.savingRule, factToCheck: profile.factToCheck, source: profile.notification,
    sourceLabel: 'Official transition notification', counterpartActId: profile.counterpartActId,
  };
}

export function displayDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number);
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(year, month - 1, day));
}

function actShortName(actId: string): string {
  return ({ ipc: 'IPC', crpc: 'CrPC', evidence: 'Evidence Act' } as Record<string, string>)[actId] ?? actId.toUpperCase();
}

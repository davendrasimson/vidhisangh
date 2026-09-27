export interface SectionCrossReference {
  actId: string;
  section: string;
  correspondingActId: string;
  correspondingSection: string;
  subject: string;
  note?: string;
}

export const CRIMINAL_LAW_COMPARISON_SOURCE = 'https://bprd.nic.in/page/documents_by_bprd';

const FORWARD_REFERENCES: SectionCrossReference[] = [
  { actId: 'ipc', section: '34', correspondingActId: 'bns', correspondingSection: '3(5)', subject: 'Acts done by several persons in furtherance of common intention' },
  { actId: 'ipc', section: '120B', correspondingActId: 'bns', correspondingSection: '61', subject: 'Criminal conspiracy' },
  { actId: 'ipc', section: '302', correspondingActId: 'bns', correspondingSection: '103', subject: 'Punishment for murder' },
  { actId: 'ipc', section: '304A', correspondingActId: 'bns', correspondingSection: '106', subject: 'Causing death by negligence', note: 'BNS section 106 contains material changes and separate sub-provisions; section 106(2) was excluded from the original commencement notification.' },
  { actId: 'ipc', section: '307', correspondingActId: 'bns', correspondingSection: '109', subject: 'Attempt to murder' },
  { actId: 'ipc', section: '354', correspondingActId: 'bns', correspondingSection: '74', subject: 'Assault or criminal force to woman with intent to outrage modesty' },
  { actId: 'ipc', section: '354A', correspondingActId: 'bns', correspondingSection: '75', subject: 'Sexual harassment' },
  { actId: 'ipc', section: '376', correspondingActId: 'bns', correspondingSection: '64', subject: 'Punishment for rape' },
  { actId: 'ipc', section: '379', correspondingActId: 'bns', correspondingSection: '303(2)', subject: 'Punishment for theft' },
  { actId: 'ipc', section: '406', correspondingActId: 'bns', correspondingSection: '316(2)', subject: 'Punishment for criminal breach of trust' },
  { actId: 'ipc', section: '420', correspondingActId: 'bns', correspondingSection: '318(4)', subject: 'Cheating and dishonestly inducing delivery of property' },
  { actId: 'ipc', section: '498A', correspondingActId: 'bns', correspondingSection: '85–86', subject: 'Cruelty by husband or relative of husband' },
  { actId: 'ipc', section: '506', correspondingActId: 'bns', correspondingSection: '351(2)–(3)', subject: 'Punishment for criminal intimidation' },

  { actId: 'crpc', section: '41', correspondingActId: 'bnss', correspondingSection: '35', subject: 'Arrest without warrant' },
  { actId: 'crpc', section: '41A', correspondingActId: 'bnss', correspondingSection: '35(3)–(6)', subject: 'Notice of appearance before police officer' },
  { actId: 'crpc', section: '154', correspondingActId: 'bnss', correspondingSection: '173', subject: 'Information in cognizable cases' },
  { actId: 'crpc', section: '161', correspondingActId: 'bnss', correspondingSection: '180', subject: 'Examination of witnesses by police' },
  { actId: 'crpc', section: '164', correspondingActId: 'bnss', correspondingSection: '183', subject: 'Recording confessions and statements' },
  { actId: 'crpc', section: '167', correspondingActId: 'bnss', correspondingSection: '187', subject: 'Remand when investigation cannot be completed in twenty-four hours' },
  { actId: 'crpc', section: '173', correspondingActId: 'bnss', correspondingSection: '193', subject: 'Police report on completion of investigation' },
  { actId: 'crpc', section: '313', correspondingActId: 'bnss', correspondingSection: '351', subject: 'Examination of accused' },
  { actId: 'crpc', section: '320', correspondingActId: 'bnss', correspondingSection: '359', subject: 'Compounding of offences' },
  { actId: 'crpc', section: '436A', correspondingActId: 'bnss', correspondingSection: '479', subject: 'Maximum detention period for undertrial prisoner' },
  { actId: 'crpc', section: '438', correspondingActId: 'bnss', correspondingSection: '482', subject: 'Anticipatory bail' },
  { actId: 'crpc', section: '439', correspondingActId: 'bnss', correspondingSection: '483', subject: 'Special bail powers of High Court or Court of Session' },
  { actId: 'crpc', section: '482', correspondingActId: 'bnss', correspondingSection: '528', subject: 'Inherent powers of High Court' },

  { actId: 'evidence', section: '24', correspondingActId: 'bsa', correspondingSection: '22', subject: 'Confession caused by inducement, threat, coercion or promise' },
  { actId: 'evidence', section: '27', correspondingActId: 'bsa', correspondingSection: '23 proviso', subject: 'Information received from accused leading to discovery' },
  { actId: 'evidence', section: '32', correspondingActId: 'bsa', correspondingSection: '26', subject: 'Statements by persons who cannot be called as witnesses' },
  { actId: 'evidence', section: '45', correspondingActId: 'bsa', correspondingSection: '39', subject: 'Opinions of experts' },
  { actId: 'evidence', section: '65B', correspondingActId: 'bsa', correspondingSection: '63', subject: 'Admissibility of electronic records' },
  { actId: 'evidence', section: '101', correspondingActId: 'bsa', correspondingSection: '104', subject: 'Burden of proof' },
];

function normalise(section: string): string {
  return section.toUpperCase().replace(/\s+/g, '').replace(/^SECTION/, '');
}

export function sectionCrossReferences(actId: string, section: string): SectionCrossReference[] {
  const sought = normalise(section).replace(/\(.*/, '');
  const forward = FORWARD_REFERENCES.filter((item) => item.actId === actId && normalise(item.section).replace(/\(.*/, '') === sought);
  const reverse = FORWARD_REFERENCES.filter((item) => item.correspondingActId === actId && normalise(item.correspondingSection).replace(/\(.*/, '').replace(/[–-].*/, '') === sought)
    .map((item) => ({
      actId,
      section: item.correspondingSection,
      correspondingActId: item.actId,
      correspondingSection: item.section,
      subject: item.subject,
      note: item.note,
    }));
  return [...forward, ...reverse];
}

import type { DraftLanguage, DraftTemplate, LocalText } from './legal-drafting-templates';

/**
 * Order formats for judicial officers (25 Oct 2026; Delhi, Punjab, Himachal
 * Pradesh and Uttarakhand added 30 Oct 2026). One body per format in English,
 * Hindi and Punjabi; the heading, case block and signature follow the court's
 * state:
 *
 * - Uttar Pradesh and Uttarakhand — Allahabad practice (the General Rules the
 *   Uttarakhand courts inherited): "IN THE COURT OF …", "Presiding Officer",
 *   JO code, "मु.अ.सं." and the Hindi judgment close.
 * - Haryana and Punjab — Punjab & Haryana High Court practice: the officer is
 *   named in the heading, UID No., "Announced in open court" and the page note
 *   under judgments. Punjab also gets the Punjabi bodies.
 * - Delhi — the district courts' heading (officer, designation, then the court
 *   complex), no officer code, "Announced in the open court on …".
 * - Himachal Pradesh — the officer named in the heading with ", H.P.", no
 *   officer code, "Announced in open court today".
 * - Anything else gets the general heading.
 *
 * DRAFTS FOR REVIEW: the UP and Haryana sets are with serving officers from
 * those states; the four new sets follow the same frame and await their own
 * reviewers. Statutory references are to the BNSS 2023 / BNS 2023 / CPC 1908 /
 * NI Act 1881.
 */
export type OrderState = 'up' | 'hr' | 'pb' | 'dl' | 'hp' | 'uk' | 'general';

export const ORDER_STATES: { id: OrderState; label: string }[] = [
  { id: 'up', label: 'Uttar Pradesh (Allahabad High Court)' },
  { id: 'uk', label: 'Uttarakhand (Uttarakhand High Court)' },
  { id: 'hr', label: 'Haryana (Punjab & Haryana High Court)' },
  { id: 'pb', label: 'Punjab (Punjab & Haryana High Court)' },
  { id: 'dl', label: 'Delhi (Delhi High Court)' },
  { id: 'hp', label: 'Himachal Pradesh (High Court of Himachal Pradesh)' },
  { id: 'general', label: 'Other state / general' },
];

/** The format set for the state in the officer's profile. */
export function orderStateFor(judicialState: string | null | undefined): OrderState {
  const s = (judicialState ?? '').toLowerCase();
  if (s.includes('uttar pradesh')) return 'up';
  if (s.includes('uttarakhand') || s.includes('uttaranchal')) return 'uk';
  if (s.includes('haryana')) return 'hr';
  if (s.includes('punjab')) return 'pb';
  if (s.includes('delhi')) return 'dl';
  if (s.includes('himachal')) return 'hp';
  return 'general';
}

/** How a state frames its orders (heading, officer code, judgment close). */
type Style = 'allahabad' | 'ph' | 'delhi' | 'hp' | 'general';
const STYLE: Record<OrderState, Style> = { up: 'allahabad', uk: 'allahabad', hr: 'ph', pb: 'ph', dl: 'delhi', hp: 'hp', general: 'general' };

/** Text in the three drafting languages; Punjabi falls back to English where a format has none yet. */
type Bilingual = { en: string; hi: string; pa?: string };
const t = (en: string, hi: string, pa = en): LocalText => ({ en, hi, pa });

/** Fields every order carries in its heading, case block and signature. */
const HEAD = ['court', 'place', 'caseNumber', 'cnr', 'firstParty', 'secondParty', 'officerCode', 'orderDate'];
const SIGN = ['judgeName', 'judgeDesignation'];
const FIR = ['firNumber', 'policeStation', 'sections'];

export const ORDER_FIELD_LABELS: Record<string, LocalText> = {
  cnr: t('CNR number', 'सी.एन.आर. संख्या', 'ਸੀ.ਐਨ.ਆਰ. ਨੰਬਰ'),
  officerCode: t('Officer code (JO code / UID No.)', 'अधिकारी कोड (जे.ओ. कोड / यू.आई.डी. नं.)', 'ਅਧਿਕਾਰੀ ਕੋਡ (ਜੇ.ਓ. ਕੋਡ / ਯੂ.ਆਈ.ਡੀ. ਨੰ.)'),
  proceedings: t('Proceedings today', 'आज की कार्यवाही', 'ਅੱਜ ਦੀ ਕਾਰਵਾਈ'),
  nextPurpose: t('Purpose of next date', 'अगली तारीख का प्रयोजन', 'ਅਗਲੀ ਤਾਰੀਖ਼ ਦਾ ਮੰਤਵ'),
  bailSection: t('Provision (e.g. Section 483 BNSS)', 'प्रावधान (जैसे धारा 483 बी.एन.एस.एस.)', 'ਵਿਵਸਥਾ (ਜਿਵੇਂ ਧਾਰਾ 483 ਬੀ.ਐਨ.ਐਸ.ਐਸ.)'),
  custodySince: t('In custody since', 'अभिरक्षा में कब से', 'ਹਿਰਾਸਤ ਵਿੱਚ ਕਦੋਂ ਤੋਂ'),
  applicantSubmissions: t('Submissions for the applicant', 'आवेदक की ओर से तर्क', 'ਬਿਨੈਕਾਰ ਵੱਲੋਂ ਦਲੀਲਾਂ'),
  prosecutionSubmissions: t('Submissions of the prosecution', 'अभियोजन की ओर से तर्क', 'ਸਰਕਾਰੀ ਪੱਖ ਵੱਲੋਂ ਦਲੀਲਾਂ'),
  defenceSubmissions: t('Submissions for the accused', 'अभियुक्त की ओर से तर्क', 'ਮੁਲਜ਼ਮ ਵੱਲੋਂ ਦਲੀਲਾਂ'),
  reasons: t('Reasons / findings', 'कारण / निष्कर्ष', 'ਕਾਰਨ / ਨਤੀਜੇ'),
  bondAmount: t('Bond amount (Rs.)', 'बंधपत्र राशि (रु.)', 'ਮੁਚਲਕੇ ਦੀ ਰਕਮ (ਰੁ.)'),
  conditions: t('Conditions', 'शर्तें', 'ਸ਼ਰਤਾਂ'),
  arrestDateTime: t('Date and time of arrest', 'गिरफ्तारी की तारीख और समय', 'ਗ੍ਰਿਫ਼ਤਾਰੀ ਦੀ ਤਾਰੀਖ਼ ਅਤੇ ਸਮਾਂ'),
  producedBy: t('Produced by (IO, rank)', 'प्रस्तुतकर्ता (विवेचक, पद)', 'ਪੇਸ਼ ਕਰਨ ਵਾਲਾ (ਤਫ਼ਤੀਸ਼ੀ ਅਫ਼ਸਰ, ਰੈਂਕ)'),
  custodySought: t('Custody sought (police / judicial)', 'मांगी गई अभिरक्षा (पुलिस / न्यायिक)', 'ਮੰਗੀ ਗਈ ਹਿਰਾਸਤ (ਪੁਲਿਸ / ਨਿਆਂਇਕ)'),
  arrestCompliance: t('Grounds of arrest, intimation, medical (Ss. 47, 48, 53 BNSS)', 'गिरफ्तारी के आधार, सूचना, चिकित्सा (धारा 47, 48, 53 बी.एन.एस.एस.)', 'ਗ੍ਰਿਫ਼ਤਾਰੀ ਦੇ ਆਧਾਰ, ਸੂਚਨਾ, ਮੈਡੀਕਲ (ਧਾਰਾ 47, 48, 53 ਬੀ.ਐਨ.ਐਸ.ਐਸ.)'),
  legalAid: t('Counsel / legal aid', 'अधिवक्ता / विधिक सहायता', 'ਵਕੀਲ / ਕਾਨੂੰਨੀ ਸਹਾਇਤਾ'),
  remandGrounds: t('Grounds for remand (IO)', 'रिमाण्ड के आधार (विवेचक)', 'ਰਿਮਾਂਡ ਦੇ ਆਧਾਰ (ਤਫ਼ਤੀਸ਼ੀ ਅਫ਼ਸਰ)'),
  accusedStatement: t('What the accused said', 'अभियुक्त का कथन', 'ਮੁਲਜ਼ਮ ਦਾ ਬਿਆਨ'),
  remandDays: t('Days of remand', 'रिमाण्ड के दिन', 'ਰਿਮਾਂਡ ਦੇ ਦਿਨ'),
  remandTill: t('Remanded till', 'रिमाण्ड की अवधि तक', 'ਰਿਮਾਂਡ ਦੀ ਮਿਆਦ ਤੱਕ'),
  prosecutionCase: t('Case of the prosecution in brief', 'अभियोजन कथानक संक्षेप में', 'ਸਰਕਾਰੀ ਪੱਖ ਦਾ ਕੇਸ ਸੰਖੇਪ ਵਿੱਚ'),
  chargeSections: t('Offences charged', 'आरोपित अपराध', 'ਆਇਦ ਦੋਸ਼'),
  chargeSection: t('Provision for charge (e.g. Section 251 BNSS)', 'आरोप का प्रावधान (जैसे धारा 251 बी.एन.एस.एस.)', 'ਦੋਸ਼ ਦੀ ਵਿਵਸਥਾ (ਜਿਵੇਂ ਧਾਰਾ 251 ਬੀ.ਐਨ.ਐਸ.ਐਸ.)'),
  cognizanceSource: t('Police report / complaint', 'पुलिस रिपोर्ट / परिवाद', 'ਪੁਲਿਸ ਰਿਪੋਰਟ / ਸ਼ਿਕਾਇਤ'),
  materialSummary: t('Material on record', 'पत्रावली पर उपलब्ध सामग्री', 'ਮਿਸਲ ਉੱਤੇ ਮੌਜੂਦ ਸਮੱਗਰੀ'),
  accusedHeard: t('Hearing of the accused (proviso to S. 223(1) BNSS)', 'अभियुक्त की सुनवाई (धारा 223(1) बी.एन.एस.एस. का परंतुक)', 'ਮੁਲਜ਼ਮ ਦੀ ਸੁਣਵਾਈ (ਧਾਰਾ 223(1) ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਦਾ ਪਰੰਤੁਕ)'),
  processType: t('Process (summons / bailable / non-bailable warrant)', 'आदेशिका (सम्मन / जमानतीय / अजमानतीय वारंट)', 'ਪ੍ਰੋਸੈਸ (ਸੰਮਨ / ਜ਼ਮਾਨਤੀ / ਗ਼ੈਰ-ਜ਼ਮਾਨਤੀ ਵਾਰੰਟ)'),
  dateInstitution: t('Date of institution', 'संस्थित होने की तारीख', 'ਦਾਇਰ ਹੋਣ ਦੀ ਤਾਰੀਖ਼'),
  dateDecision: t('Date of decision', 'निर्णय की तारीख', 'ਫ਼ੈਸਲੇ ਦੀ ਤਾਰੀਖ਼'),
  chargeDetails: t('Charge framed', 'विरचित आरोप', 'ਆਇਦ ਕੀਤਾ ਦੋਸ਼'),
  prosecutionEvidence: t('Prosecution evidence (PWs, exhibits)', 'अभियोजन साक्ष्य (अ.सा., प्रदर्श)', 'ਸਰਕਾਰੀ ਪੱਖ ਦੀ ਗਵਾਹੀ (ਪੀ.ਡਬਲਯੂ., ਐਗਜ਼ੀਬਿਟ)'),
  accusedStatement351: t('Statement of the accused (S. 351 BNSS)', 'अभियुक्त का बयान (धारा 351 बी.एन.एस.एस.)', 'ਮੁਲਜ਼ਮ ਦਾ ਬਿਆਨ (ਧਾਰਾ 351 ਬੀ.ਐਨ.ਐਸ.ਐਸ.)'),
  defenceEvidence: t('Defence evidence', 'बचाव साक्ष्य', 'ਸਫ਼ਾਈ ਪੱਖ ਦੀ ਗਵਾਹੀ'),
  arguments: t('Arguments', 'तर्क', 'ਦਲੀਲਾਂ'),
  pointsForDetermination: t('Points for determination', 'अवधारणीय बिन्दु', 'ਨਿਰਣੇ ਲਈ ਨੁਕਤੇ'),
  findings: t('Findings with reasons', 'सकारण निष्कर्ष', 'ਕਾਰਨਾਂ ਸਹਿਤ ਨਤੀਜੇ'),
  conclusion: t('Conclusion and result', 'निष्कर्ष एवं परिणाम', 'ਸਿੱਟਾ ਅਤੇ ਨਤੀਜਾ'),
  chequeDetails: t('Cheque (number, date, amount, drawee bank)', 'चेक (संख्या, तारीख, राशि, बैंक)', 'ਚੈੱਕ (ਨੰਬਰ, ਤਾਰੀਖ਼, ਰਕਮ, ਬੈਂਕ)'),
  dishonourDate: t('Date of return memo', 'चेक अनादरण मेमो की तारीख', 'ਵਾਪਸੀ ਮੀਮੋ ਦੀ ਤਾਰੀਖ਼'),
  dishonourReason: t('Reason for return', 'अनादरण का कारण', 'ਵਾਪਸੀ ਦਾ ਕਾਰਨ'),
  noticeDate: t('Date of demand notice', 'मांग नोटिस की तारीख', 'ਮੰਗ ਨੋਟਿਸ ਦੀ ਤਾਰੀਖ਼'),
  noticeServed: t('Notice served on', 'नोटिस तामील की तारीख', 'ਨੋਟਿਸ ਤਾਮੀਲ ਦੀ ਤਾਰੀਖ਼'),
  complaintFiled: t('Complaint filed on', 'परिवाद दायर करने की तारीख', 'ਸ਼ਿਕਾਇਤ ਦਾਇਰ ਕਰਨ ਦੀ ਤਾਰੀਖ਼'),
  jurisdiction: t('Territorial jurisdiction (S. 142(2))', 'क्षेत्रीय अधिकारिता (धारा 142(2))', 'ਇਲਾਕਾਈ ਅਧਿਕਾਰ ਖੇਤਰ (ਧਾਰਾ 142(2))'),
  preliminaryEvidence: t('Preliminary evidence', 'प्रारम्भिक साक्ष्य', 'ਮੁੱਢਲੀ ਗਵਾਹੀ'),
  plaintCase: t('Case of the plaintiff', 'वादी का कथन', 'ਮੁਦਈ ਦਾ ਕੇਸ'),
  defence: t('Defence / reply', 'प्रतिवादी का कथन / उत्तर', 'ਮੁਦਾਲੇ ਦਾ ਕੇਸ / ਜਵਾਬ'),
  issues: t('Issues (with onus)', 'वाद बिन्दु (भार सबूत सहित)', 'ਮੁੱਦੇ (ਸਬੂਤ ਦੇ ਭਾਰ ਸਹਿਤ)'),
  primaFacie: t('Prima facie case', 'प्रथम दृष्टया मामला', 'ਮੁੱਢਲੀ ਨਜ਼ਰੇ ਕੇਸ'),
  balance: t('Balance of convenience', 'सुविधा का संतुलन', 'ਸਹੂਲਤ ਦਾ ਸੰਤੁਲਨ'),
  irreparable: t('Irreparable injury', 'अपूरणीय क्षति', 'ਨਾ-ਪੂਰਨਯੋਗ ਨੁਕਸਾਨ'),
  operative: t('Operative order', 'प्रभावी आदेश', 'ਪ੍ਰਭਾਵੀ ਹੁਕਮ'),
  suitNature: t('Nature of suit', 'वाद की प्रकृति', 'ਦਾਵੇ ਦੀ ਕਿਸਮ'),
  claim: t('Claim / relief sought', 'दावा / मांगा गया अनुतोष', 'ਦਾਵਾ / ਮੰਗੀ ਗਈ ਰਾਹਤ'),
  decreeTerms: t('Terms of the decree', 'डिक्री की शर्तें', 'ਡਿਕਰੀ ਦੀਆਂ ਸ਼ਰਤਾਂ'),
  costs: t('Costs of the suit', 'वाद व्यय', 'ਦਾਵੇ ਦਾ ਖ਼ਰਚਾ'),
  applicantCase: t('Case of the applicant(s)', 'आवेदक(गण) का कथन', 'ਬਿਨੈਕਾਰ(ਾਂ) ਦਾ ਕੇਸ'),
  respondentCase: t('Case of the respondent', 'विपक्षी का कथन', 'ਜਵਾਬਦੇਹ ਦਾ ਕੇਸ'),
  affidavitsFiled: t('Affidavits of assets and liabilities', 'आस्तियों और दायित्वों के शपथपत्र', 'ਜਾਇਦਾਦ ਅਤੇ ਦੇਣਦਾਰੀਆਂ ਦੇ ਹਲਫ਼ੀਆ ਬਿਆਨ'),
  incomeFindings: t('Income and needs', 'आय और आवश्यकताएँ', 'ਆਮਦਨ ਅਤੇ ਲੋੜਾਂ'),
  amount: t('Amount per month (Rs.)', 'मासिक राशि (रु.)', 'ਮਹੀਨਾਵਾਰ ਰਕਮ (ਰੁ.)'),
  effectiveFrom: t('Payable from', 'कब से देय', 'ਕਦੋਂ ਤੋਂ ਦੇਣਯੋਗ'),
};

/** Fields written as paragraphs rather than one line. */
export const ORDER_LONG_FIELDS = new Set([
  'proceedings', 'applicantSubmissions', 'prosecutionSubmissions', 'defenceSubmissions', 'reasons', 'conditions',
  'arrestCompliance', 'remandGrounds', 'accusedStatement', 'prosecutionCase', 'materialSummary', 'accusedHeard',
  'chargeDetails', 'prosecutionEvidence', 'accusedStatement351', 'defenceEvidence', 'arguments',
  'pointsForDetermination', 'findings', 'conclusion', 'preliminaryEvidence', 'plaintCase', 'defence', 'issues',
  'primaFacie', 'balance', 'irreparable', 'operative', 'decreeTerms', 'costs', 'applicantCase', 'respondentCase',
  'affidavitsFiled', 'incomeFindings', 'claim',
]);

export interface OrderFormat extends DraftTemplate {
  /** Order body with {{field}} placeholders; the heading and signature are added around it. */
  body: Bilingual;
  /** Standard wording a field starts with (switched with the language while untouched). */
  defaults?: Record<string, Bilingual>;
  /** A judgment (closing words and, in Punjab & Haryana practice, the page note). */
  judgment?: boolean;
}

const BAIL_CONDITIONS: Bilingual = {
  en: '(i) The applicant shall appear before the court on every date of hearing unless exempted;\n(ii) shall not directly or indirectly make any inducement, threat or promise to any person acquainted with the facts of the case, or tamper with the evidence;\n(iii) shall not commit an offence similar to the offence of which he/she is accused;\n(iv) shall not leave India without the prior permission of the court.',
  hi: '(i) आवेदक प्रत्येक नियत तिथि पर न्यायालय में उपस्थित रहेगा, जब तक कि उसे छूट न दी जाए;\n(ii) मामले के तथ्यों से परिचित किसी व्यक्ति को प्रत्यक्ष या अप्रत्यक्ष रूप से कोई प्रलोभन, धमकी या वचन नहीं देगा, और न ही साक्ष्य से छेड़छाड़ करेगा;\n(iii) उसी प्रकृति का कोई अपराध नहीं करेगा जिसका उस पर आरोप है;\n(iv) न्यायालय की पूर्व अनुमति के बिना भारत से बाहर नहीं जाएगा।',
  pa: '(i) ਬਿਨੈਕਾਰ ਹਰ ਪੇਸ਼ੀ ਦੀ ਤਾਰੀਖ਼ ਨੂੰ ਅਦਾਲਤ ਵਿੱਚ ਹਾਜ਼ਰ ਰਹੇਗਾ, ਜਦੋਂ ਤੱਕ ਉਸ ਨੂੰ ਛੋਟ ਨਾ ਦਿੱਤੀ ਜਾਵੇ;\n(ii) ਕੇਸ ਦੇ ਤੱਥਾਂ ਤੋਂ ਵਾਕਿਫ਼ ਕਿਸੇ ਵਿਅਕਤੀ ਨੂੰ ਸਿੱਧੇ ਜਾਂ ਅਸਿੱਧੇ ਤੌਰ ਉੱਤੇ ਕੋਈ ਲਾਲਚ, ਧਮਕੀ ਜਾਂ ਵਾਅਦਾ ਨਹੀਂ ਕਰੇਗਾ, ਅਤੇ ਨਾ ਹੀ ਸਬੂਤਾਂ ਨਾਲ ਛੇੜਛਾੜ ਕਰੇਗਾ;\n(iii) ਉਸ ਕਿਸਮ ਦਾ ਕੋਈ ਜੁਰਮ ਨਹੀਂ ਕਰੇਗਾ ਜਿਸ ਦਾ ਉਸ ਉੱਤੇ ਦੋਸ਼ ਹੈ;\n(iv) ਅਦਾਲਤ ਦੀ ਅਗਾਊਂ ਇਜਾਜ਼ਤ ਬਿਨਾਂ ਭਾਰਤ ਤੋਂ ਬਾਹਰ ਨਹੀਂ ਜਾਵੇਗਾ।',
};

const ANTICIPATORY_CONDITIONS: Bilingual = {
  en: '(i) The applicant shall make himself/herself available for interrogation by a police officer as and when required;\n(ii) shall not directly or indirectly make any inducement, threat or promise to any person acquainted with the facts of the case so as to dissuade him from disclosing such facts to the court or to any police officer;\n(iii) shall not leave India without the previous permission of the court;\n(iv) shall join the investigation within seven days from today.',
  hi: '(i) आवेदक आवश्यकता होने पर पुलिस अधिकारी द्वारा पूछताछ हेतु स्वयं को उपलब्ध कराएगा;\n(ii) मामले के तथ्यों से परिचित किसी व्यक्ति को ऐसे तथ्य न्यायालय या किसी पुलिस अधिकारी के समक्ष प्रकट करने से रोकने के लिए प्रत्यक्ष या अप्रत्यक्ष रूप से कोई प्रलोभन, धमकी या वचन नहीं देगा;\n(iii) न्यायालय की पूर्व अनुमति के बिना भारत से बाहर नहीं जाएगा;\n(iv) आज से सात दिन के भीतर विवेचना में सम्मिलित होगा।',
  pa: '(i) ਬਿਨੈਕਾਰ ਲੋੜ ਪੈਣ ਉੱਤੇ ਪੁਲਿਸ ਅਫ਼ਸਰ ਦੁਆਰਾ ਪੁੱਛਗਿੱਛ ਲਈ ਆਪਣੇ ਆਪ ਨੂੰ ਉਪਲਬਧ ਕਰਵਾਏਗਾ;\n(ii) ਕੇਸ ਦੇ ਤੱਥਾਂ ਤੋਂ ਵਾਕਿਫ਼ ਕਿਸੇ ਵਿਅਕਤੀ ਨੂੰ ਅਜਿਹੇ ਤੱਥ ਅਦਾਲਤ ਜਾਂ ਕਿਸੇ ਪੁਲਿਸ ਅਫ਼ਸਰ ਸਾਹਮਣੇ ਪ੍ਰਗਟ ਕਰਨ ਤੋਂ ਰੋਕਣ ਲਈ ਸਿੱਧੇ ਜਾਂ ਅਸਿੱਧੇ ਤੌਰ ਉੱਤੇ ਕੋਈ ਲਾਲਚ, ਧਮਕੀ ਜਾਂ ਵਾਅਦਾ ਨਹੀਂ ਕਰੇਗਾ;\n(iii) ਅਦਾਲਤ ਦੀ ਅਗਾਊਂ ਇਜਾਜ਼ਤ ਬਿਨਾਂ ਭਾਰਤ ਤੋਂ ਬਾਹਰ ਨਹੀਂ ਜਾਵੇਗਾ;\n(iv) ਅੱਜ ਤੋਂ ਸੱਤ ਦਿਨਾਂ ਦੇ ਅੰਦਰ ਤਫ਼ਤੀਸ਼ ਵਿੱਚ ਸ਼ਾਮਲ ਹੋਵੇਗਾ।',
};

const ISSUES: Bilingual = {
  en: '1. Whether the plaintiff is entitled to a decree of ________ as prayed for? OPP\n2. Whether the suit is not maintainable in its present form? OPD\n3. Whether the plaintiff has no cause of action or locus standi to file the suit? OPD\n4. Whether the suit is bad for non-joinder / mis-joinder of necessary parties? OPD\n5. Relief.',
  hi: '1. क्या वादी ________ की डिक्री पाने का अधिकारी है, जैसा कि प्रार्थित है? (भार सबूत वादी पर)\n2. क्या वाद वर्तमान स्वरूप में पोषणीय नहीं है? (भार सबूत प्रतिवादी पर)\n3. क्या वादी को वाद संस्थित करने का वाद कारण अथवा अधिकार प्राप्त नहीं है? (भार सबूत प्रतिवादी पर)\n4. क्या वाद आवश्यक पक्षकारों के असंयोजन / कुसंयोजन से दूषित है? (भार सबूत प्रतिवादी पर)\n5. अनुतोष?',
  pa: '1. ਕੀ ਮੁਦਈ ________ ਦੀ ਡਿਕਰੀ ਲੈਣ ਦਾ ਹੱਕਦਾਰ ਹੈ, ਜਿਵੇਂ ਮੰਗ ਕੀਤੀ ਗਈ ਹੈ? OPP\n2. ਕੀ ਦਾਵਾ ਆਪਣੇ ਮੌਜੂਦਾ ਰੂਪ ਵਿੱਚ ਚੱਲਣਯੋਗ ਨਹੀਂ ਹੈ? OPD\n3. ਕੀ ਮੁਦਈ ਨੂੰ ਦਾਵਾ ਦਾਇਰ ਕਰਨ ਦਾ ਕੋਈ ਕਾਰਨ ਜਾਂ ਹੱਕ ਨਹੀਂ ਹੈ? OPD\n4. ਕੀ ਦਾਵਾ ਜ਼ਰੂਰੀ ਧਿਰਾਂ ਦੇ ਸ਼ਾਮਲ ਨਾ ਹੋਣ / ਗ਼ਲਤ ਸ਼ਾਮਲ ਹੋਣ ਕਾਰਨ ਦੂਸ਼ਿਤ ਹੈ? OPD\n5. ਰਾਹਤ।',
};

const COSTS: Bilingual = {
  en: 'Particulars | Plaintiff | Defendant\nCourt fee on plaint / written statement | Rs. ____ | Rs. ____\nProcess fee | Rs. ____ | Rs. ____\nCounsel’s fee | Rs. ____ | Rs. ____\nOther expenses | Rs. ____ | Rs. ____\nTotal | Rs. ____ | Rs. ____',
  hi: 'विवरण | वादी | प्रतिवादी\nवादपत्र / प्रतिवादपत्र पर न्याय शुल्क | रु. ____ | रु. ____\nआदेशिका शुल्क | रु. ____ | रु. ____\nअधिवक्ता शुल्क | रु. ____ | रु. ____\nअन्य व्यय | रु. ____ | रु. ____\nयोग | रु. ____ | रु. ____',
  pa: 'ਵੇਰਵਾ | ਮੁਦਈ | ਮੁਦਾਲਾ\nਦਾਵੇ / ਲਿਖਤੀ ਬਿਆਨ ਉੱਤੇ ਕੋਰਟ ਫ਼ੀਸ | ਰੁ. ____ | ਰੁ. ____\nਪ੍ਰੋਸੈਸ ਫ਼ੀਸ | ਰੁ. ____ | ਰੁ. ____\nਵਕੀਲ ਦੀ ਫ਼ੀਸ | ਰੁ. ____ | ਰੁ. ____\nਹੋਰ ਖ਼ਰਚੇ | ਰੁ. ____ | ਰੁ. ____\nਕੁੱਲ | ਰੁ. ____ | ਰੁ. ____',
};

const order = (
  id: string, icon: string, category: DraftTemplate['category'], title: LocalText, description: LocalText,
  purpose: LocalText, fields: string[], tags: string[], body: Bilingual, extra: Partial<OrderFormat> = {},
): OrderFormat => ({
  id, icon, category, roles: ['judicial'], kind: 'order', title, description, purpose,
  fields: [...HEAD, ...fields, ...SIGN], tags, body, ...extra,
});

export const JUDICIAL_ORDER_FORMATS: OrderFormat[] = [
  order('judicial-daily-order', 'event_note', 'judicial',
    t('Order sheet (daily order)', 'आदेश पत्रक (दैनिक आदेश)', 'ਜ਼ਿਮਨੀ ਹੁਕਮ (ਰੋਜ਼ਾਨਾ ਹੁਕਮ)'),
    t('Presence, proceedings of the day and the next date with its purpose.', 'उपस्थिति, दिन की कार्यवाही तथा अगली तारीख और उसका प्रयोजन।', 'ਹਾਜ਼ਰੀ, ਦਿਨ ਦੀ ਕਾਰਵਾਈ ਅਤੇ ਅਗਲੀ ਤਾਰੀਖ਼ ਤੇ ਉਸ ਦਾ ਮੰਤਵ।'),
    t('Order sheet', 'आदेश पत्रक', 'ਜ਼ਿਮਨੀ ਹੁਕਮ'),
    ['appearances', 'proceedings', 'nextDate', 'nextPurpose'], ['daily order', 'order sheet', 'zimni', 'roznama', 'next date'],
    {
      en: 'Present: {{appearances}}\n\n{{proceedings}}\n\nTo come up on {{nextDate}} for {{nextPurpose}}.',
      hi: 'उपस्थित: {{appearances}}\n\n{{proceedings}}\n\nपत्रावली दिनांक {{nextDate}} को {{nextPurpose}} हेतु पेश हो।',
      pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n{{proceedings}}\n\nਮਿਸਲ {{nextDate}} ਨੂੰ {{nextPurpose}} ਲਈ ਪੇਸ਼ ਹੋਵੇ।',
    }),

  order('judicial-speaking-order', 'account_balance', 'judicial',
    t('Speaking judicial order', 'कारणयुक्त न्यायिक आदेश', 'ਤਰਕਸੰਗਤ ਨਿਆਂਇਕ ਹੁਕਮ'),
    t('Cause title, appearances, reasons, directions and signature block.', 'वाद शीर्षक, उपस्थिति, कारण, निर्देश और हस्ताक्षर खंड।', 'ਕੇਸ ਸਿਰਲੇਖ, ਹਾਜ਼ਰੀ, ਕਾਰਨ, ਨਿਰਦੇਸ਼ ਅਤੇ ਦਸਤਖ਼ਤ।'),
    t('Order', 'आदेश', 'ਹੁਕਮ'),
    ['appearances', 'orderBody'], ['judge', 'judicial officer', 'speaking order', 'decision', 'directions'],
    { en: 'Present: {{appearances}}\n\n{{orderBody}}', hi: 'उपस्थित: {{appearances}}\n\n{{orderBody}}', pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n{{orderBody}}' }),

  order('judicial-interim-order', 'balance', 'judicial',
    t('Interim order', 'अंतरिम आदेश', 'ਅੰਤਰਿਮ ਹੁਕਮ'),
    t('Interim relief with submissions, findings and operative directions.', 'दलीलों, निष्कर्षों और प्रभावी निर्देशों सहित अंतरिम राहत।', 'ਦਲੀਲਾਂ, ਨਤੀਜਿਆਂ ਅਤੇ ਪ੍ਰਭਾਵੀ ਨਿਰਦੇਸ਼ਾਂ ਸਮੇਤ ਅੰਤਰਿਮ ਰਾਹਤ।'),
    t('Interim order', 'अंतरिम आदेश', 'ਅੰਤਰਿਮ ਹੁਕਮ'),
    ['appearances', 'orderBody'], ['interim order', 'stay', 'interim relief'],
    { en: 'Present: {{appearances}}\n\n{{orderBody}}', hi: 'उपस्थित: {{appearances}}\n\n{{orderBody}}', pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n{{orderBody}}' }),

  order('judicial-regular-bail', 'lock_open', 'criminal',
    t('Bail order (regular bail)', 'जमानत आदेश (नियमित जमानत)', 'ਜ਼ਮਾਨਤ ਦਾ ਹੁਕਮ (ਰੈਗੂਲਰ ਜ਼ਮਾਨਤ)'),
    t('Sections 480 / 483 BNSS: custody, submissions, reasons, bond and conditions.', 'धारा 480 / 483 बी.एन.एस.एस.: अभिरक्षा, तर्क, कारण, बंधपत्र और शर्तें।', 'ਧਾਰਾ 480 / 483 ਬੀ.ਐਨ.ਐਸ.ਐਸ.: ਹਿਰਾਸਤ, ਦਲੀਲਾਂ, ਕਾਰਨ, ਮੁਚਲਕਾ ਅਤੇ ਸ਼ਰਤਾਂ।'),
    t('Order on application for regular bail', 'नियमित जमानत प्रार्थना पत्र पर आदेश', 'ਰੈਗੂਲਰ ਜ਼ਮਾਨਤ ਦੀ ਦਰਖ਼ਾਸਤ ਉੱਤੇ ਹੁਕਮ'),
    [...FIR, 'bailSection', 'custodySince', 'appearances', 'applicantSubmissions', 'prosecutionSubmissions', 'reasons', 'bondAmount', 'conditions'],
    ['bail', 'regular bail', 'bnss 480', 'bnss 483', 'custody'],
    {
      en: 'Present: {{appearances}}\n\n1. This is an application under {{bailSection}} for grant of regular bail moved on behalf of the applicant/accused {{secondParty}}, who is in judicial custody since {{custodySince}} in FIR No. {{firNumber}}, Police Station {{policeStation}}, for the offences punishable under {{sections}}.\n\n2. Learned counsel for the applicant submitted that {{applicantSubmissions}}\n\n3. Learned Public Prosecutor for the State opposed the application and submitted that {{prosecutionSubmissions}}\n\n4. I have heard both sides and perused the record, including the reply / status report of the investigating officer.\n\n5. {{reasons}}\n\n6. In view of the above, the application is [allowed / dismissed]. The applicant/accused {{secondParty}} is ordered to be released on bail on furnishing a personal bond in the sum of Rs. {{bondAmount}} with [one / two] surety(ies) in the like amount to the satisfaction of the court [concerned / Duty Magistrate], subject to the following conditions:\n{{conditions}}\n\n7. Nothing stated herein shall be taken as an expression of opinion on the merits of the case.\n\n8. The application stands disposed of. A copy of this order be sent to the Superintendent of the jail concerned and be placed on the main file.',
      hi: 'उपस्थित: {{appearances}}\n\n1. यह प्रार्थना पत्र {{bailSection}} के अंतर्गत आवेदक/अभियुक्त {{secondParty}} की ओर से नियमित जमानत हेतु प्रस्तुत किया गया है, जो मु.अ.सं./एफ.आई.आर. सं. {{firNumber}}, थाना {{policeStation}}, धारा {{sections}} के अंतर्गत दिनांक {{custodySince}} से न्यायिक अभिरक्षा में है।\n\n2. आवेदक के विद्वान अधिवक्ता का तर्क है कि {{applicantSubmissions}}\n\n3. राज्य की ओर से विद्वान लोक अभियोजक ने प्रार्थना पत्र का विरोध करते हुए तर्क दिया कि {{prosecutionSubmissions}}\n\n4. मैंने उभय पक्ष को सुना तथा विवेचक की आख्या / स्थिति रिपोर्ट सहित पत्रावली का अवलोकन किया।\n\n5. {{reasons}}\n\n6. उपरोक्त विवेचन के आधार पर प्रार्थना पत्र [स्वीकार / अस्वीकार] किया जाता है। आवेदक/अभियुक्त {{secondParty}} को रु. {{bondAmount}} का व्यक्तिगत बंधपत्र तथा इतनी ही राशि के [एक / दो] प्रतिभू संबंधित न्यायालय की संतुष्टि के अनुसार प्रस्तुत करने पर निम्नलिखित शर्तों के अधीन जमानत पर रिहा किया जाए:\n{{conditions}}\n\n7. इस आदेश में की गई कोई टिप्पणी मामले के गुण-दोष पर राय नहीं मानी जाएगी।\n\n8. प्रार्थना पत्र निस्तारित किया जाता है। आदेश की प्रति संबंधित कारागार अधीक्षक को भेजी जाए तथा मूल पत्रावली पर रखी जाए।',
      pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n1. ਇਹ ਦਰਖ਼ਾਸਤ {{bailSection}} ਅਧੀਨ ਬਿਨੈਕਾਰ/ਮੁਲਜ਼ਮ {{secondParty}} ਵੱਲੋਂ ਰੈਗੂਲਰ ਜ਼ਮਾਨਤ ਲਈ ਦਿੱਤੀ ਗਈ ਹੈ, ਜੋ ਐਫ.ਆਈ.ਆਰ. ਨੰ. {{firNumber}}, ਥਾਣਾ {{policeStation}}, ਧਾਰਾ {{sections}} ਅਧੀਨ ਸਜ਼ਾਯੋਗ ਜੁਰਮਾਂ ਵਿੱਚ ਮਿਤੀ {{custodySince}} ਤੋਂ ਨਿਆਂਇਕ ਹਿਰਾਸਤ ਵਿੱਚ ਹੈ।\n\n2. ਬਿਨੈਕਾਰ ਦੇ ਵਿਦਵਾਨ ਵਕੀਲ ਨੇ ਦਲੀਲ ਦਿੱਤੀ ਕਿ {{applicantSubmissions}}\n\n3. ਰਾਜ ਵੱਲੋਂ ਵਿਦਵਾਨ ਸਰਕਾਰੀ ਵਕੀਲ ਨੇ ਦਰਖ਼ਾਸਤ ਦਾ ਵਿਰੋਧ ਕਰਦਿਆਂ ਦਲੀਲ ਦਿੱਤੀ ਕਿ {{prosecutionSubmissions}}\n\n4. ਮੈਂ ਦੋਹਾਂ ਪੱਖਾਂ ਨੂੰ ਸੁਣਿਆ ਅਤੇ ਤਫ਼ਤੀਸ਼ੀ ਅਫ਼ਸਰ ਦੇ ਜਵਾਬ / ਸਟੇਟਸ ਰਿਪੋਰਟ ਸਮੇਤ ਮਿਸਲ ਦਾ ਅਧਿਐਨ ਕੀਤਾ।\n\n5. {{reasons}}\n\n6. ਉਪਰੋਕਤ ਦੇ ਮੱਦੇਨਜ਼ਰ ਦਰਖ਼ਾਸਤ [ਮਨਜ਼ੂਰ / ਖ਼ਾਰਜ] ਕੀਤੀ ਜਾਂਦੀ ਹੈ। ਬਿਨੈਕਾਰ/ਮੁਲਜ਼ਮ {{secondParty}} ਨੂੰ {{bondAmount}} ਰੁਪਏ ਦਾ ਨਿੱਜੀ ਮੁਚਲਕਾ ਅਤੇ ਇੰਨੀ ਹੀ ਰਕਮ ਦਾ/ਦੇ [ਇੱਕ / ਦੋ] ਜ਼ਾਮਨ ਸਬੰਧਤ ਅਦਾਲਤ / ਡਿਊਟੀ ਮੈਜਿਸਟ੍ਰੇਟ ਦੀ ਤਸੱਲੀ ਅਨੁਸਾਰ ਪੇਸ਼ ਕਰਨ ਉੱਤੇ ਹੇਠ ਲਿਖੀਆਂ ਸ਼ਰਤਾਂ ਅਧੀਨ ਜ਼ਮਾਨਤ ਉੱਤੇ ਰਿਹਾਅ ਕੀਤਾ ਜਾਵੇ:\n{{conditions}}\n\n7. ਇਸ ਹੁਕਮ ਵਿੱਚ ਕਹੀ ਕੋਈ ਗੱਲ ਕੇਸ ਦੀ ਮੈਰਿਟ ਉੱਤੇ ਰਾਇ ਨਹੀਂ ਮੰਨੀ ਜਾਵੇਗੀ।\n\n8. ਦਰਖ਼ਾਸਤ ਦਾ ਨਿਪਟਾਰਾ ਕੀਤਾ ਜਾਂਦਾ ਹੈ। ਇਸ ਹੁਕਮ ਦੀ ਨਕਲ ਸਬੰਧਤ ਜੇਲ੍ਹ ਸੁਪਰਡੈਂਟ ਨੂੰ ਭੇਜੀ ਜਾਵੇ ਅਤੇ ਮੁੱਖ ਮਿਸਲ ਉੱਤੇ ਰੱਖੀ ਜਾਵੇ।',
    },
    { defaults: { conditions: BAIL_CONDITIONS, bailSection: { en: 'Section 483 of the Bharatiya Nagarik Suraksha Sanhita, 2023', hi: 'भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 483', pa: 'ਭਾਰਤੀ ਨਾਗਰਿਕ ਸੁਰੱਖਿਆ ਸੰਹਿਤਾ, 2023 ਦੀ ਧਾਰਾ 483' } } }),

  order('judicial-anticipatory-bail', 'shield', 'criminal',
    t('Anticipatory bail order', 'अग्रिम जमानत आदेश', 'ਅਗਾਊਂ ਜ਼ਮਾਨਤ ਦਾ ਹੁਕਮ'),
    t('Section 482 BNSS: accusation, submissions, reasons and the Section 482(2) conditions.', 'धारा 482 बी.एन.एस.एस.: आरोप, तर्क, कारण और धारा 482(2) की शर्तें।', 'ਧਾਰਾ 482 ਬੀ.ਐਨ.ਐਸ.ਐਸ.: ਦੋਸ਼, ਦਲੀਲਾਂ, ਕਾਰਨ ਅਤੇ ਧਾਰਾ 482(2) ਦੀਆਂ ਸ਼ਰਤਾਂ।'),
    t('Order on application under Section 482 BNSS for anticipatory bail', 'अग्रिम जमानत हेतु धारा 482 बी.एन.एस.एस. के अंतर्गत प्रार्थना पत्र पर आदेश', 'ਅਗਾਊਂ ਜ਼ਮਾਨਤ ਲਈ ਧਾਰਾ 482 ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਅਧੀਨ ਦਰਖ਼ਾਸਤ ਉੱਤੇ ਹੁਕਮ'),
    [...FIR, 'appearances', 'applicantSubmissions', 'prosecutionSubmissions', 'reasons', 'bondAmount', 'conditions'],
    ['anticipatory bail', 'bnss 482', 'arrest'],
    {
      en: 'Present: {{appearances}}\n\n1. The applicant {{secondParty}} apprehends arrest in FIR No. {{firNumber}}, Police Station {{policeStation}}, registered for the offences punishable under {{sections}}, and seeks a direction under Section 482 of the Bharatiya Nagarik Suraksha Sanhita, 2023 that in the event of arrest he/she be released on bail.\n\n2. Learned counsel for the applicant submitted that {{applicantSubmissions}}\n\n3. Learned Public Prosecutor for the State, on instructions from the investigating officer, opposed the application and submitted that {{prosecutionSubmissions}}\n\n4. I have considered the nature and gravity of the accusation, the role attributed to the applicant, his/her antecedents, the possibility of the applicant fleeing from justice and of tampering with the evidence, and the stage of the investigation.\n\n5. {{reasons}}\n\n6. Accordingly, the application is [allowed / dismissed]. In the event of arrest, the applicant shall be released on bail on furnishing a personal bond in the sum of Rs. {{bondAmount}} with one surety in the like amount to the satisfaction of the arresting officer / investigating officer, subject to the following conditions under Section 482(2) BNSS:\n{{conditions}}\n\n7. Nothing herein shall be construed as an expression of opinion on the merits of the case. The application stands disposed of.',
      hi: 'उपस्थित: {{appearances}}\n\n1. आवेदक {{secondParty}} को मु.अ.सं./एफ.आई.आर. सं. {{firNumber}}, थाना {{policeStation}}, धारा {{sections}} में गिरफ्तारी की आशंका है तथा उसने भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 482 के अंतर्गत यह निर्देश चाहा है कि गिरफ्तारी की दशा में उसे जमानत पर रिहा किया जाए।\n\n2. आवेदक के विद्वान अधिवक्ता का तर्क है कि {{applicantSubmissions}}\n\n3. विवेचक से प्राप्त निर्देशों के आधार पर राज्य की ओर से विद्वान लोक अभियोजक ने प्रार्थना पत्र का विरोध करते हुए तर्क दिया कि {{prosecutionSubmissions}}\n\n4. मैंने आरोप की प्रकृति एवं गंभीरता, आवेदक की भूमिका, उसके पूर्ववृत्त, उसके न्याय से भागने एवं साक्ष्य से छेड़छाड़ की संभावना तथा विवेचना की प्रावस्था पर विचार किया।\n\n5. {{reasons}}\n\n6. अतः प्रार्थना पत्र [स्वीकार / अस्वीकार] किया जाता है। गिरफ्तारी की दशा में आवेदक को रु. {{bondAmount}} का व्यक्तिगत बंधपत्र तथा इतनी ही राशि का एक प्रतिभू गिरफ्तार करने वाले अधिकारी / विवेचक की संतुष्टि के अनुसार प्रस्तुत करने पर धारा 482(2) बी.एन.एस.एस. की निम्नलिखित शर्तों के अधीन जमानत पर रिहा किया जाए:\n{{conditions}}\n\n7. इस आदेश की कोई टिप्पणी मामले के गुण-दोष पर राय नहीं मानी जाएगी। प्रार्थना पत्र निस्तारित किया जाता है।',
      pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n1. ਬਿਨੈਕਾਰ {{secondParty}} ਨੂੰ ਐਫ.ਆਈ.ਆਰ. ਨੰ. {{firNumber}}, ਥਾਣਾ {{policeStation}}, ਧਾਰਾ {{sections}} ਅਧੀਨ ਦਰਜ ਕੇਸ ਵਿੱਚ ਗ੍ਰਿਫ਼ਤਾਰੀ ਦਾ ਡਰ ਹੈ ਅਤੇ ਉਸ ਨੇ ਭਾਰਤੀ ਨਾਗਰਿਕ ਸੁਰੱਖਿਆ ਸੰਹਿਤਾ, 2023 ਦੀ ਧਾਰਾ 482 ਅਧੀਨ ਇਹ ਹਦਾਇਤ ਮੰਗੀ ਹੈ ਕਿ ਗ੍ਰਿਫ਼ਤਾਰੀ ਦੀ ਸੂਰਤ ਵਿੱਚ ਉਸ ਨੂੰ ਜ਼ਮਾਨਤ ਉੱਤੇ ਰਿਹਾਅ ਕੀਤਾ ਜਾਵੇ।\n\n2. ਬਿਨੈਕਾਰ ਦੇ ਵਿਦਵਾਨ ਵਕੀਲ ਨੇ ਦਲੀਲ ਦਿੱਤੀ ਕਿ {{applicantSubmissions}}\n\n3. ਤਫ਼ਤੀਸ਼ੀ ਅਫ਼ਸਰ ਤੋਂ ਮਿਲੀਆਂ ਹਦਾਇਤਾਂ ਉੱਤੇ ਰਾਜ ਵੱਲੋਂ ਵਿਦਵਾਨ ਸਰਕਾਰੀ ਵਕੀਲ ਨੇ ਦਰਖ਼ਾਸਤ ਦਾ ਵਿਰੋਧ ਕਰਦਿਆਂ ਦਲੀਲ ਦਿੱਤੀ ਕਿ {{prosecutionSubmissions}}\n\n4. ਮੈਂ ਦੋਸ਼ ਦੀ ਕਿਸਮ ਅਤੇ ਗੰਭੀਰਤਾ, ਬਿਨੈਕਾਰ ਦੀ ਭੂਮਿਕਾ, ਉਸ ਦੇ ਪਿਛੋਕੜ, ਉਸ ਦੇ ਨਿਆਂ ਤੋਂ ਭੱਜਣ ਅਤੇ ਸਬੂਤਾਂ ਨਾਲ ਛੇੜਛਾੜ ਦੀ ਸੰਭਾਵਨਾ ਅਤੇ ਤਫ਼ਤੀਸ਼ ਦੇ ਪੜਾਅ ਉੱਤੇ ਵਿਚਾਰ ਕੀਤਾ।\n\n5. {{reasons}}\n\n6. ਇਸ ਲਈ ਦਰਖ਼ਾਸਤ [ਮਨਜ਼ੂਰ / ਖ਼ਾਰਜ] ਕੀਤੀ ਜਾਂਦੀ ਹੈ। ਗ੍ਰਿਫ਼ਤਾਰੀ ਦੀ ਸੂਰਤ ਵਿੱਚ ਬਿਨੈਕਾਰ ਨੂੰ {{bondAmount}} ਰੁਪਏ ਦਾ ਨਿੱਜੀ ਮੁਚਲਕਾ ਅਤੇ ਇੰਨੀ ਹੀ ਰਕਮ ਦਾ ਇੱਕ ਜ਼ਾਮਨ ਗ੍ਰਿਫ਼ਤਾਰ ਕਰਨ ਵਾਲੇ ਅਫ਼ਸਰ / ਤਫ਼ਤੀਸ਼ੀ ਅਫ਼ਸਰ ਦੀ ਤਸੱਲੀ ਅਨੁਸਾਰ ਪੇਸ਼ ਕਰਨ ਉੱਤੇ ਧਾਰਾ 482(2) ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਦੀਆਂ ਹੇਠ ਲਿਖੀਆਂ ਸ਼ਰਤਾਂ ਅਧੀਨ ਜ਼ਮਾਨਤ ਉੱਤੇ ਰਿਹਾਅ ਕੀਤਾ ਜਾਵੇ:\n{{conditions}}\n\n7. ਇਸ ਹੁਕਮ ਵਿੱਚ ਕਹੀ ਕੋਈ ਗੱਲ ਕੇਸ ਦੀ ਮੈਰਿਟ ਉੱਤੇ ਰਾਇ ਨਹੀਂ ਮੰਨੀ ਜਾਵੇਗੀ। ਦਰਖ਼ਾਸਤ ਦਾ ਨਿਪਟਾਰਾ ਕੀਤਾ ਜਾਂਦਾ ਹੈ।',
    },
    { defaults: { conditions: ANTICIPATORY_CONDITIONS } }),

  order('judicial-remand', 'gavel', 'criminal',
    t('Remand order', 'रिमाण्ड आदेश', 'ਰਿਮਾਂਡ ਦਾ ਹੁਕਮ'),
    t('Section 187 BNSS: production, arrest safeguards, grounds and period of custody.', 'धारा 187 बी.एन.एस.एस.: प्रस्तुति, गिरफ्तारी संबंधी सुरक्षा उपाय, आधार और अभिरक्षा की अवधि।', 'ਧਾਰਾ 187 ਬੀ.ਐਨ.ਐਸ.ਐਸ.: ਪੇਸ਼ੀ, ਗ੍ਰਿਫ਼ਤਾਰੀ ਦੇ ਸੁਰੱਖਿਆ ਉਪਾਅ, ਆਧਾਰ ਅਤੇ ਹਿਰਾਸਤ ਦੀ ਮਿਆਦ।'),
    t('Remand order under Section 187 BNSS', 'धारा 187 बी.एन.एस.एस. के अंतर्गत रिमाण्ड आदेश', 'ਧਾਰਾ 187 ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਅਧੀਨ ਰਿਮਾਂਡ ਦਾ ਹੁਕਮ'),
    [...FIR, 'arrestDateTime', 'producedBy', 'custodySought', 'arrestCompliance', 'legalAid', 'remandGrounds', 'accusedStatement', 'reasons', 'remandDays', 'remandTill'],
    ['remand', 'police custody', 'judicial custody', 'bnss 187', 'production'],
    {
      en: '1. Accused {{secondParty}}, arrested on {{arrestDateTime}} in FIR No. {{firNumber}}, Police Station {{policeStation}}, for the offences punishable under {{sections}}, has been produced by {{producedBy}} with an application seeking {{custodySought}} custody, along with a copy of the entries in the case diary.\n\n2. The accused has been produced within twenty-four hours of arrest, excluding the time of journey. Compliance with the safeguards of arrest has been checked: {{arrestCompliance}}\n\n3. The accused was informed of his/her right to be defended by an advocate of his/her choice or through legal aid: {{legalAid}}\n\n4. The investigating officer submitted that {{remandGrounds}}\n\n5. On being asked, the accused stated that {{accusedStatement}}\n\n6. I have perused the case diary and the material placed before me. {{reasons}}\n\n7. Accordingly, the accused {{secondParty}} is remanded to {{custodySought}} custody for {{remandDays}} days, i.e. till {{remandTill}}, and shall be produced before the court on that date. Warrant of custody be prepared accordingly.',
      hi: '1. अभियुक्त {{secondParty}}, जिसे दिनांक {{arrestDateTime}} को मु.अ.सं./एफ.आई.आर. सं. {{firNumber}}, थाना {{policeStation}}, धारा {{sections}} में गिरफ्तार किया गया, {{producedBy}} द्वारा {{custodySought}} अभिरक्षा हेतु प्रार्थना पत्र एवं केस डायरी की प्रविष्टियों की प्रति के साथ प्रस्तुत किया गया।\n\n2. अभियुक्त को यात्रा के समय को छोड़कर गिरफ्तारी के चौबीस घंटे के भीतर प्रस्तुत किया गया है। गिरफ्तारी संबंधी सुरक्षा उपायों के अनुपालन की जाँच की गई: {{arrestCompliance}}\n\n3. अभियुक्त को अपनी पसंद के अधिवक्ता अथवा विधिक सहायता के माध्यम से प्रतिरक्षा के अधिकार से अवगत कराया गया: {{legalAid}}\n\n4. विवेचक का कथन है कि {{remandGrounds}}\n\n5. पूछे जाने पर अभियुक्त ने कहा कि {{accusedStatement}}\n\n6. मैंने केस डायरी एवं प्रस्तुत सामग्री का अवलोकन किया। {{reasons}}\n\n7. अतः अभियुक्त {{secondParty}} को {{remandDays}} दिन अर्थात दिनांक {{remandTill}} तक {{custodySought}} अभिरक्षा में रिमाण्ड किया जाता है तथा उसे उक्त तिथि पर न्यायालय के समक्ष प्रस्तुत किया जाए। तदनुसार अभिरक्षा वारंट तैयार किया जाए।',
      pa: '1. ਮੁਲਜ਼ਮ {{secondParty}}, ਜਿਸ ਨੂੰ {{arrestDateTime}} ਨੂੰ ਐਫ.ਆਈ.ਆਰ. ਨੰ. {{firNumber}}, ਥਾਣਾ {{policeStation}}, ਧਾਰਾ {{sections}} ਵਿੱਚ ਗ੍ਰਿਫ਼ਤਾਰ ਕੀਤਾ ਗਿਆ, ਨੂੰ {{producedBy}} ਵੱਲੋਂ {{custodySought}} ਹਿਰਾਸਤ ਦੀ ਦਰਖ਼ਾਸਤ ਅਤੇ ਕੇਸ ਡਾਇਰੀ ਦੀਆਂ ਐਂਟਰੀਆਂ ਦੀ ਨਕਲ ਸਮੇਤ ਪੇਸ਼ ਕੀਤਾ ਗਿਆ ਹੈ।\n\n2. ਮੁਲਜ਼ਮ ਨੂੰ ਸਫ਼ਰ ਦਾ ਸਮਾਂ ਛੱਡ ਕੇ ਗ੍ਰਿਫ਼ਤਾਰੀ ਦੇ ਚੌਵੀ ਘੰਟਿਆਂ ਦੇ ਅੰਦਰ ਪੇਸ਼ ਕੀਤਾ ਗਿਆ ਹੈ। ਗ੍ਰਿਫ਼ਤਾਰੀ ਦੇ ਸੁਰੱਖਿਆ ਉਪਾਵਾਂ ਦੀ ਪਾਲਣਾ ਦੀ ਜਾਂਚ ਕੀਤੀ ਗਈ: {{arrestCompliance}}\n\n3. ਮੁਲਜ਼ਮ ਨੂੰ ਆਪਣੀ ਪਸੰਦ ਦੇ ਵਕੀਲ ਜਾਂ ਕਾਨੂੰਨੀ ਸਹਾਇਤਾ ਰਾਹੀਂ ਸਫ਼ਾਈ ਦੇ ਹੱਕ ਬਾਰੇ ਦੱਸਿਆ ਗਿਆ: {{legalAid}}\n\n4. ਤਫ਼ਤੀਸ਼ੀ ਅਫ਼ਸਰ ਨੇ ਕਿਹਾ ਕਿ {{remandGrounds}}\n\n5. ਪੁੱਛਣ ਉੱਤੇ ਮੁਲਜ਼ਮ ਨੇ ਕਿਹਾ ਕਿ {{accusedStatement}}\n\n6. ਮੈਂ ਕੇਸ ਡਾਇਰੀ ਅਤੇ ਮੇਰੇ ਸਾਹਮਣੇ ਰੱਖੀ ਸਮੱਗਰੀ ਦਾ ਅਧਿਐਨ ਕੀਤਾ। {{reasons}}\n\n7. ਇਸ ਲਈ ਮੁਲਜ਼ਮ {{secondParty}} ਨੂੰ {{remandDays}} ਦਿਨਾਂ ਲਈ, ਭਾਵ {{remandTill}} ਤੱਕ, {{custodySought}} ਹਿਰਾਸਤ ਵਿੱਚ ਰਿਮਾਂਡ ਕੀਤਾ ਜਾਂਦਾ ਹੈ ਅਤੇ ਉਸ ਨੂੰ ਉਸ ਤਾਰੀਖ਼ ਨੂੰ ਅਦਾਲਤ ਸਾਹਮਣੇ ਪੇਸ਼ ਕੀਤਾ ਜਾਵੇ। ਹਿਰਾਸਤ ਦਾ ਵਾਰੰਟ ਉਸੇ ਅਨੁਸਾਰ ਤਿਆਰ ਕੀਤਾ ਜਾਵੇ।',
    }),

  order('judicial-charge', 'rule', 'criminal',
    t('Order on charge', 'आरोप पर आदेश', 'ਦੋਸ਼ ਉੱਤੇ ਹੁਕਮ'),
    t('Arguments on charge, prima facie view, charge framed and read over, next date for evidence.', 'आरोप पर तर्क, प्रथम दृष्टया मत, आरोप विरचित कर पढ़कर सुनाया गया, साक्ष्य हेतु अगली तारीख।', 'ਦੋਸ਼ ਉੱਤੇ ਦਲੀਲਾਂ, ਮੁੱਢਲੀ ਨਜ਼ਰੇ ਰਾਇ, ਦੋਸ਼ ਆਇਦ ਕਰ ਕੇ ਪੜ੍ਹ ਕੇ ਸੁਣਾਇਆ, ਗਵਾਹੀ ਲਈ ਅਗਲੀ ਤਾਰੀਖ਼।'),
    t('Order on charge', 'आरोप पर आदेश', 'ਦੋਸ਼ ਉੱਤੇ ਹੁਕਮ'),
    [...FIR, 'appearances', 'prosecutionCase', 'defenceSubmissions', 'reasons', 'chargeSections', 'chargeSection', 'nextDate'],
    ['charge', 'framing of charge', 'discharge', 'bnss 251', 'bnss 263'],
    {
      en: 'Present: {{appearances}}\n\n1. Arguments on the point of charge have been heard from the learned Public Prosecutor for the State and learned counsel for the accused, and the record has been perused.\n\n2. Briefly stated, the case of the prosecution is that {{prosecutionCase}}\n\n3. Learned counsel for the accused submitted that {{defenceSubmissions}}\n\n4. At this stage the court is only to see whether there is ground for presuming that the accused has committed the offence; the material is not to be weighed meticulously, nor is a mini trial to be held.\n\n5. {{reasons}}\n\n6. A prima facie case is therefore made out against the accused {{secondParty}} for the offences punishable under {{chargeSections}}. Charge under {{chargeSection}} has been framed separately, read over and explained to the accused in the language understood by him/her, to which he/she pleaded not guilty and claimed trial.\n\n7. The case is now fixed for prosecution evidence. Summon the prosecution witnesses for {{nextDate}}.',
      hi: 'उपस्थित: {{appearances}}\n\n1. आरोप के बिन्दु पर राज्य की ओर से विद्वान लोक अभियोजक तथा अभियुक्त के विद्वान अधिवक्ता के तर्क सुने गए तथा पत्रावली का अवलोकन किया गया।\n\n2. संक्षेप में अभियोजन कथानक इस प्रकार है कि {{prosecutionCase}}\n\n3. अभियुक्त के विद्वान अधिवक्ता का तर्क है कि {{defenceSubmissions}}\n\n4. इस प्रावस्था पर न्यायालय को केवल यह देखना है कि क्या यह उपधारणा करने का आधार है कि अभियुक्त ने अपराध किया है; साक्ष्य का सूक्ष्म मूल्यांकन अथवा लघु विचारण नहीं किया जाना है।\n\n5. {{reasons}}\n\n6. अतः अभियुक्त {{secondParty}} के विरुद्ध {{chargeSections}} के अंतर्गत दण्डनीय अपराधों हेतु प्रथम दृष्टया मामला बनता है। {{chargeSection}} के अंतर्गत आरोप पृथक से विरचित कर अभियुक्त को उसकी समझ की भाषा में पढ़कर सुनाया व समझाया गया, जिस पर अभियुक्त ने अपराध से इन्कार कर विचारण की मांग की।\n\n7. पत्रावली अभियोजन साक्ष्य हेतु नियत की जाती है। अभियोजन साक्षीगण दिनांक {{nextDate}} हेतु तलब हों।',
      pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n1. ਦੋਸ਼ ਦੇ ਨੁਕਤੇ ਉੱਤੇ ਰਾਜ ਵੱਲੋਂ ਵਿਦਵਾਨ ਸਰਕਾਰੀ ਵਕੀਲ ਅਤੇ ਮੁਲਜ਼ਮ ਦੇ ਵਿਦਵਾਨ ਵਕੀਲ ਦੀਆਂ ਦਲੀਲਾਂ ਸੁਣੀਆਂ ਗਈਆਂ ਅਤੇ ਮਿਸਲ ਦਾ ਅਧਿਐਨ ਕੀਤਾ ਗਿਆ।\n\n2. ਸੰਖੇਪ ਵਿੱਚ ਸਰਕਾਰੀ ਪੱਖ ਦਾ ਕੇਸ ਇਹ ਹੈ ਕਿ {{prosecutionCase}}\n\n3. ਮੁਲਜ਼ਮ ਦੇ ਵਿਦਵਾਨ ਵਕੀਲ ਨੇ ਦਲੀਲ ਦਿੱਤੀ ਕਿ {{defenceSubmissions}}\n\n4. ਇਸ ਪੜਾਅ ਉੱਤੇ ਅਦਾਲਤ ਨੇ ਸਿਰਫ਼ ਇਹ ਵੇਖਣਾ ਹੈ ਕਿ ਕੀ ਇਹ ਮੰਨਣ ਦਾ ਆਧਾਰ ਹੈ ਕਿ ਮੁਲਜ਼ਮ ਨੇ ਜੁਰਮ ਕੀਤਾ ਹੈ; ਸਮੱਗਰੀ ਦੀ ਬਾਰੀਕ ਪੜਚੋਲ ਜਾਂ ਛੋਟਾ ਮੁਕੱਦਮਾ ਨਹੀਂ ਚਲਾਉਣਾ ਹੈ।\n\n5. {{reasons}}\n\n6. ਇਸ ਲਈ ਮੁਲਜ਼ਮ {{secondParty}} ਵਿਰੁੱਧ {{chargeSections}} ਅਧੀਨ ਸਜ਼ਾਯੋਗ ਜੁਰਮਾਂ ਲਈ ਮੁੱਢਲੀ ਨਜ਼ਰੇ ਕੇਸ ਬਣਦਾ ਹੈ। {{chargeSection}} ਅਧੀਨ ਦੋਸ਼ ਵੱਖਰੇ ਤੌਰ ਉੱਤੇ ਆਇਦ ਕਰ ਕੇ ਮੁਲਜ਼ਮ ਨੂੰ ਉਸ ਦੀ ਸਮਝ ਦੀ ਭਾਸ਼ਾ ਵਿੱਚ ਪੜ੍ਹ ਕੇ ਸੁਣਾਇਆ ਤੇ ਸਮਝਾਇਆ ਗਿਆ, ਜਿਸ ਉੱਤੇ ਉਸ ਨੇ ਆਪਣੇ ਆਪ ਨੂੰ ਬੇਕਸੂਰ ਕਿਹਾ ਅਤੇ ਮੁਕੱਦਮੇ ਦੀ ਮੰਗ ਕੀਤੀ।\n\n7. ਕੇਸ ਹੁਣ ਸਰਕਾਰੀ ਪੱਖ ਦੀ ਗਵਾਹੀ ਲਈ ਨਿਯਤ ਕੀਤਾ ਜਾਂਦਾ ਹੈ। ਸਰਕਾਰੀ ਗਵਾਹਾਂ ਨੂੰ {{nextDate}} ਲਈ ਸੰਮਨ ਕੀਤਾ ਜਾਵੇ।',
    },
    { defaults: { chargeSection: { en: 'Section 251 of the Bharatiya Nagarik Suraksha Sanhita, 2023', hi: 'भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 251', pa: 'ਭਾਰਤੀ ਨਾਗਰਿਕ ਸੁਰੱਖਿਆ ਸੰਹਿਤਾ, 2023 ਦੀ ਧਾਰਾ 251' } } }),

  order('judicial-cognizance', 'outgoing_mail', 'criminal',
    t('Cognizance and summons / warrant', 'संज्ञान एवं सम्मन / वारंट आदेश', 'ਸੰਗਿਆਨ ਅਤੇ ਸੰਮਨ / ਵਾਰੰਟ'),
    t('Sections 210, 223 and 227 BNSS: cognizance on a police report or complaint and issue of process.', 'धारा 210, 223 एवं 227 बी.एन.एस.एस.: पुलिस रिपोर्ट या परिवाद पर संज्ञान और आदेशिका जारी करना।', 'ਧਾਰਾ 210, 223 ਅਤੇ 227 ਬੀ.ਐਨ.ਐਸ.ਐਸ.: ਪੁਲਿਸ ਰਿਪੋਰਟ ਜਾਂ ਸ਼ਿਕਾਇਤ ਉੱਤੇ ਸੰਗਿਆਨ ਅਤੇ ਪ੍ਰੋਸੈਸ ਜਾਰੀ ਕਰਨਾ।'),
    t('Order on cognizance and issue of process', 'संज्ञान एवं आदेशिका जारी करने हेतु आदेश', 'ਸੰਗਿਆਨ ਅਤੇ ਪ੍ਰੋਸੈਸ ਜਾਰੀ ਕਰਨ ਬਾਰੇ ਹੁਕਮ'),
    [...FIR, 'cognizanceSource', 'materialSummary', 'accusedHeard', 'reasons', 'processType', 'nextDate'],
    ['cognizance', 'summons', 'warrant', 'process', 'bnss 210', 'bnss 227', 'chargesheet'],
    {
      en: '1. {{cognizanceSource}} has been received against the accused {{secondParty}} for the offences punishable under {{sections}}.\n\n2. I have perused the record and the documents filed with it: {{materialSummary}}\n\n3. [Complaint cases] In terms of the proviso to Section 223(1) BNSS, the accused was given an opportunity of being heard before cognizance: {{accusedHeard}}\n\n4. {{reasons}}\n\n5. There is sufficient ground for proceeding against the accused. Cognizance of the offences punishable under {{sections}} is taken under Section 210 of the Bharatiya Nagarik Suraksha Sanhita, 2023.\n\n6. Let the accused {{secondParty}} be summoned through {{processType}} under Section 227 BNSS for {{nextDate}}, on the filing of process fee and the list of prosecution witnesses. In a complaint case, a copy of the complaint shall accompany the process.',
      hi: '1. अभियुक्त {{secondParty}} के विरुद्ध धारा {{sections}} के अंतर्गत दण्डनीय अपराधों हेतु {{cognizanceSource}} प्राप्त हुई / हुआ है।\n\n2. मैंने पत्रावली एवं उसके साथ प्रस्तुत अभिलेखों का अवलोकन किया: {{materialSummary}}\n\n3. [परिवाद वाद में] धारा 223(1) बी.एन.एस.एस. के परंतुक के अनुसार संज्ञान से पूर्व अभियुक्त को सुनवाई का अवसर दिया गया: {{accusedHeard}}\n\n4. {{reasons}}\n\n5. अभियुक्त के विरुद्ध कार्यवाही हेतु पर्याप्त आधार है। भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 210 के अंतर्गत धारा {{sections}} के अपराधों का संज्ञान लिया जाता है।\n\n6. आदेशिका शुल्क एवं अभियोजन साक्षियों की सूची प्रस्तुत होने पर अभियुक्त {{secondParty}} को धारा 227 बी.एन.एस.एस. के अंतर्गत {{processType}} द्वारा दिनांक {{nextDate}} हेतु तलब किया जाए। परिवाद वाद में आदेशिका के साथ परिवाद की प्रति भेजी जाए।',
      pa: '1. ਮੁਲਜ਼ਮ {{secondParty}} ਵਿਰੁੱਧ ਧਾਰਾ {{sections}} ਅਧੀਨ ਸਜ਼ਾਯੋਗ ਜੁਰਮਾਂ ਲਈ {{cognizanceSource}} ਪ੍ਰਾਪਤ ਹੋਈ ਹੈ।\n\n2. ਮੈਂ ਮਿਸਲ ਅਤੇ ਉਸ ਨਾਲ ਦਾਇਰ ਦਸਤਾਵੇਜ਼ਾਂ ਦਾ ਅਧਿਐਨ ਕੀਤਾ: {{materialSummary}}\n\n3. [ਸ਼ਿਕਾਇਤ ਕੇਸਾਂ ਵਿੱਚ] ਧਾਰਾ 223(1) ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਦੇ ਪਰੰਤੁਕ ਅਨੁਸਾਰ ਸੰਗਿਆਨ ਤੋਂ ਪਹਿਲਾਂ ਮੁਲਜ਼ਮ ਨੂੰ ਸੁਣਵਾਈ ਦਾ ਮੌਕਾ ਦਿੱਤਾ ਗਿਆ: {{accusedHeard}}\n\n4. {{reasons}}\n\n5. ਮੁਲਜ਼ਮ ਵਿਰੁੱਧ ਕਾਰਵਾਈ ਲਈ ਕਾਫ਼ੀ ਆਧਾਰ ਹੈ। ਭਾਰਤੀ ਨਾਗਰਿਕ ਸੁਰੱਖਿਆ ਸੰਹਿਤਾ, 2023 ਦੀ ਧਾਰਾ 210 ਅਧੀਨ ਧਾਰਾ {{sections}} ਦੇ ਜੁਰਮਾਂ ਦਾ ਸੰਗਿਆਨ ਲਿਆ ਜਾਂਦਾ ਹੈ।\n\n6. ਪ੍ਰੋਸੈਸ ਫ਼ੀਸ ਅਤੇ ਸਰਕਾਰੀ ਗਵਾਹਾਂ ਦੀ ਸੂਚੀ ਦਾਇਰ ਹੋਣ ਉੱਤੇ ਮੁਲਜ਼ਮ {{secondParty}} ਨੂੰ ਧਾਰਾ 227 ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਅਧੀਨ {{processType}} ਰਾਹੀਂ {{nextDate}} ਲਈ ਸੰਮਨ ਕੀਤਾ ਜਾਵੇ। ਸ਼ਿਕਾਇਤ ਕੇਸ ਵਿੱਚ ਪ੍ਰੋਸੈਸ ਨਾਲ ਸ਼ਿਕਾਇਤ ਦੀ ਨਕਲ ਭੇਜੀ ਜਾਵੇ।',
    }),

  order('judicial-criminal-judgment', 'menu_book', 'criminal',
    t('Criminal judgment (frame)', 'आपराधिक निर्णय (ढाँचा)', 'ਫ਼ੌਜਦਾਰੀ ਫ਼ੈਸਲਾ (ਢਾਂਚਾ)'),
    t('Institution and decision dates, facts, charge, evidence, S. 351 statement, points, findings, result.', 'संस्थित और निर्णय की तारीख, तथ्य, आरोप, साक्ष्य, धारा 351 का बयान, बिन्दु, निष्कर्ष, परिणाम।', 'ਦਾਇਰ ਅਤੇ ਫ਼ੈਸਲੇ ਦੀਆਂ ਤਾਰੀਖ਼ਾਂ, ਤੱਥ, ਦੋਸ਼, ਗਵਾਹੀ, ਧਾਰਾ 351 ਦਾ ਬਿਆਨ, ਨੁਕਤੇ, ਨਤੀਜੇ, ਸਿੱਟਾ।'),
    t('Judgment', 'निर्णय', 'ਫ਼ੈਸਲਾ'),
    [...FIR, 'dateInstitution', 'dateDecision', 'appearances', 'prosecutionCase', 'chargeDetails', 'prosecutionEvidence', 'accusedStatement351', 'defenceEvidence', 'arguments', 'pointsForDetermination', 'findings', 'conclusion'],
    ['judgment', 'conviction', 'acquittal', 'sessions trial', 'bnss 392', 'bnss 393'],
    {
      en: 'Date of institution: {{dateInstitution}}\nDate of decision: {{dateDecision}}\n\nPresent: {{appearances}}\n\n1. The accused {{secondParty}} has been sent up for trial in FIR No. {{firNumber}}, Police Station {{policeStation}}, for the offences punishable under {{sections}}.\n\n2. Briefly stated, the case of the prosecution is that {{prosecutionCase}}\n\n3. Charge: {{chargeDetails}} The accused pleaded not guilty and claimed trial.\n\n4. Prosecution evidence: {{prosecutionEvidence}}\n\n5. Statement of the accused under Section 351 BNSS: {{accusedStatement351}}\n\n6. Defence evidence: {{defenceEvidence}}\n\n7. Arguments: {{arguments}}\n\n8. Points for determination:\n{{pointsForDetermination}}\n\n9. Findings with reasons:\n{{findings}}\n\n10. Conclusion: {{conclusion}}\n\n[If acquitted:] The accused is acquitted of the charge. His/her bail bonds stand discharged; he/she shall furnish a bond under Section 481 BNSS. [If convicted:] The accused is convicted; let him/her be heard on the question of sentence.\n\nFile be consigned to the record room after due compliance.',
      hi: 'संस्थित होने की तारीख: {{dateInstitution}}\nनिर्णय की तारीख: {{dateDecision}}\n\nउपस्थित: {{appearances}}\n\n1. अभियुक्त {{secondParty}} का विचारण मु.अ.सं./एफ.आई.आर. सं. {{firNumber}}, थाना {{policeStation}}, धारा {{sections}} के अंतर्गत दण्डनीय अपराधों हेतु किया गया है।\n\n2. संक्षेप में अभियोजन कथानक इस प्रकार है कि {{prosecutionCase}}\n\n3. आरोप: {{chargeDetails}} अभियुक्त ने अपराध से इन्कार कर विचारण की मांग की।\n\n4. अभियोजन साक्ष्य: {{prosecutionEvidence}}\n\n5. धारा 351 बी.एन.एस.एस. के अंतर्गत अभियुक्त का बयान: {{accusedStatement351}}\n\n6. बचाव साक्ष्य: {{defenceEvidence}}\n\n7. तर्क: {{arguments}}\n\n8. अवधारणीय बिन्दु:\n{{pointsForDetermination}}\n\n9. सकारण निष्कर्ष:\n{{findings}}\n\n10. निष्कर्ष: {{conclusion}}\n\n[दोषमुक्ति की दशा में:] अभियुक्त को आरोपित अपराध से दोषमुक्त किया जाता है। उसके जमानतनामे उन्मोचित किए जाते हैं; वह धारा 481 बी.एन.एस.एस. के अंतर्गत बंधपत्र प्रस्तुत करे। [दोषसिद्धि की दशा में:] अभियुक्त को दोषसिद्ध किया जाता है; दण्ड के प्रश्न पर उसे सुना जाए।\n\nआवश्यक अनुपालन के पश्चात पत्रावली दाखिल दफ्तर हो।',
      pa: 'ਦਾਇਰ ਹੋਣ ਦੀ ਤਾਰੀਖ਼: {{dateInstitution}}\nਫ਼ੈਸਲੇ ਦੀ ਤਾਰੀਖ਼: {{dateDecision}}\n\nਹਾਜ਼ਰ: {{appearances}}\n\n1. ਮੁਲਜ਼ਮ {{secondParty}} ਨੂੰ ਐਫ.ਆਈ.ਆਰ. ਨੰ. {{firNumber}}, ਥਾਣਾ {{policeStation}}, ਧਾਰਾ {{sections}} ਅਧੀਨ ਸਜ਼ਾਯੋਗ ਜੁਰਮਾਂ ਲਈ ਮੁਕੱਦਮੇ ਲਈ ਭੇਜਿਆ ਗਿਆ ਹੈ।\n\n2. ਸੰਖੇਪ ਵਿੱਚ ਸਰਕਾਰੀ ਪੱਖ ਦਾ ਕੇਸ ਇਹ ਹੈ ਕਿ {{prosecutionCase}}\n\n3. ਦੋਸ਼: {{chargeDetails}} ਮੁਲਜ਼ਮ ਨੇ ਆਪਣੇ ਆਪ ਨੂੰ ਬੇਕਸੂਰ ਕਿਹਾ ਅਤੇ ਮੁਕੱਦਮੇ ਦੀ ਮੰਗ ਕੀਤੀ।\n\n4. ਸਰਕਾਰੀ ਪੱਖ ਦੀ ਗਵਾਹੀ: {{prosecutionEvidence}}\n\n5. ਧਾਰਾ 351 ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਅਧੀਨ ਮੁਲਜ਼ਮ ਦਾ ਬਿਆਨ: {{accusedStatement351}}\n\n6. ਸਫ਼ਾਈ ਪੱਖ ਦੀ ਗਵਾਹੀ: {{defenceEvidence}}\n\n7. ਦਲੀਲਾਂ: {{arguments}}\n\n8. ਨਿਰਣੇ ਲਈ ਨੁਕਤੇ:\n{{pointsForDetermination}}\n\n9. ਕਾਰਨਾਂ ਸਹਿਤ ਨਤੀਜੇ:\n{{findings}}\n\n10. ਸਿੱਟਾ: {{conclusion}}\n\n[ਬਰੀ ਹੋਣ ਦੀ ਸੂਰਤ ਵਿੱਚ:] ਮੁਲਜ਼ਮ ਨੂੰ ਦੋਸ਼ ਤੋਂ ਬਰੀ ਕੀਤਾ ਜਾਂਦਾ ਹੈ। ਉਸ ਦੇ ਜ਼ਮਾਨਤੀ ਮੁਚਲਕੇ ਖ਼ਾਰਜ ਕੀਤੇ ਜਾਂਦੇ ਹਨ; ਉਹ ਧਾਰਾ 481 ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਅਧੀਨ ਮੁਚਲਕਾ ਪੇਸ਼ ਕਰੇ। [ਦੋਸ਼ੀ ਠਹਿਰਾਉਣ ਦੀ ਸੂਰਤ ਵਿੱਚ:] ਮੁਲਜ਼ਮ ਨੂੰ ਦੋਸ਼ੀ ਠਹਿਰਾਇਆ ਜਾਂਦਾ ਹੈ; ਸਜ਼ਾ ਦੇ ਸਵਾਲ ਉੱਤੇ ਉਸ ਨੂੰ ਸੁਣਿਆ ਜਾਵੇ।\n\nਲੋੜੀਂਦੀ ਪਾਲਣਾ ਤੋਂ ਬਾਅਦ ਮਿਸਲ ਰਿਕਾਰਡ ਰੂਮ ਵਿੱਚ ਦਾਖ਼ਲ ਕੀਤੀ ਜਾਵੇ।',
    },
    { judgment: true }),

  order('judicial-ni-138', 'receipt_long', 'criminal',
    t('Section 138 NI Act: summoning order', 'धारा 138 एन.आई. एक्ट: तलबी आदेश', 'ਧਾਰਾ 138 ਐਨ.ਆਈ. ਐਕਟ: ਸੰਮਨ ਕਰਨ ਦਾ ਹੁਕਮ'),
    t('Cheque, dishonour, notice, limitation, jurisdiction, preliminary evidence and summons.', 'चेक, अनादरण, नोटिस, परिसीमा, अधिकारिता, प्रारम्भिक साक्ष्य और सम्मन।', 'ਚੈੱਕ, ਅਨਾਦਰ, ਨੋਟਿਸ, ਮਿਆਦ, ਅਧਿਕਾਰ ਖੇਤਰ, ਮੁੱਢਲੀ ਗਵਾਹੀ ਅਤੇ ਸੰਮਨ।'),
    t('Order on cognizance: complaint under Section 138 of the Negotiable Instruments Act, 1881', 'संज्ञान आदेश: परक्राम्य लिखत अधिनियम, 1881 की धारा 138 के अंतर्गत परिवाद', 'ਸੰਗਿਆਨ ਦਾ ਹੁਕਮ: ਨੈਗੋਸ਼ੀਏਬਲ ਇੰਸਟਰੂਮੈਂਟਸ ਐਕਟ, 1881 ਦੀ ਧਾਰਾ 138 ਅਧੀਨ ਸ਼ਿਕਾਇਤ'),
    ['chequeDetails', 'dishonourDate', 'dishonourReason', 'noticeDate', 'noticeServed', 'complaintFiled', 'jurisdiction', 'preliminaryEvidence', 'accusedHeard', 'nextDate'],
    ['cheque bounce', 'ni act', 'section 138', 'negotiable instruments', 'summoning'],
    {
      en: '1. The complainant {{firstParty}} alleges that the accused {{secondParty}} issued cheque {{chequeDetails}} in discharge of a legally enforceable debt or liability, which was returned unpaid by the bank by memo dated {{dishonourDate}} with the remarks "{{dishonourReason}}".\n\n2. A demand notice dated {{noticeDate}} was sent within thirty days of the information of dishonour and was served on {{noticeServed}}. The amount was not paid within fifteen days of its receipt. The complaint was filed on {{complaintFiled}}, within one month of the cause of action, as required by Section 142(1)(b) of the Act.\n\n3. This court has territorial jurisdiction under Section 142(2) of the Act: {{jurisdiction}}\n\n4. Preliminary evidence (by affidavit under Section 145 of the Act): {{preliminaryEvidence}}\n\n5. In terms of the proviso to Section 223(1) BNSS, the accused was given an opportunity of being heard before cognizance: {{accusedHeard}}\n\n6. The record discloses, prima facie, the ingredients of the offence under Section 138 of the Negotiable Instruments Act, 1881. Cognizance is taken. Let the accused {{secondParty}} be summoned for {{nextDate}} on the filing of process fee, through the ordinary mode and also by e-mail / electronic means where the address is available.',
      hi: '1. परिवादी {{firstParty}} का कथन है कि अभियुक्त {{secondParty}} ने विधितः प्रवर्तनीय ऋण अथवा दायित्व के उन्मोचन में चेक {{chequeDetails}} जारी किया, जो बैंक द्वारा दिनांक {{dishonourDate}} के मेमो से "{{dishonourReason}}" टिप्पणी के साथ अनादरित होकर वापस किया गया।\n\n2. अनादरण की सूचना के तीस दिन के भीतर दिनांक {{noticeDate}} का मांग नोटिस भेजा गया जो दिनांक {{noticeServed}} को तामील हुआ। नोटिस प्राप्ति के पंद्रह दिन के भीतर भुगतान नहीं किया गया। परिवाद दिनांक {{complaintFiled}} को, अधिनियम की धारा 142(1)(ख) के अनुसार वाद कारण उत्पन्न होने के एक माह के भीतर, प्रस्तुत किया गया।\n\n3. अधिनियम की धारा 142(2) के अंतर्गत इस न्यायालय को क्षेत्रीय अधिकारिता प्राप्त है: {{jurisdiction}}\n\n4. प्रारम्भिक साक्ष्य (अधिनियम की धारा 145 के अंतर्गत शपथपत्र द्वारा): {{preliminaryEvidence}}\n\n5. धारा 223(1) बी.एन.एस.एस. के परंतुक के अनुसार संज्ञान से पूर्व अभियुक्त को सुनवाई का अवसर दिया गया: {{accusedHeard}}\n\n6. पत्रावली से प्रथम दृष्टया परक्राम्य लिखत अधिनियम, 1881 की धारा 138 के अपराध के तत्व प्रकट होते हैं। संज्ञान लिया जाता है। आदेशिका शुल्क प्रस्तुत होने पर अभियुक्त {{secondParty}} को सामान्य प्रक्रिया तथा पता उपलब्ध होने पर ई-मेल / इलेक्ट्रॉनिक माध्यम से भी दिनांक {{nextDate}} हेतु तलब किया जाए।',
      pa: '1. ਸ਼ਿਕਾਇਤਕਰਤਾ {{firstParty}} ਦਾ ਕਹਿਣਾ ਹੈ ਕਿ ਮੁਲਜ਼ਮ {{secondParty}} ਨੇ ਕਾਨੂੰਨੀ ਤੌਰ ਉੱਤੇ ਵਸੂਲਣਯੋਗ ਕਰਜ਼ੇ ਜਾਂ ਦੇਣਦਾਰੀ ਦੀ ਅਦਾਇਗੀ ਲਈ ਚੈੱਕ {{chequeDetails}} ਜਾਰੀ ਕੀਤਾ, ਜੋ ਬੈਂਕ ਵੱਲੋਂ ਮਿਤੀ {{dishonourDate}} ਦੇ ਮੀਮੋ ਨਾਲ "{{dishonourReason}}" ਟਿੱਪਣੀ ਸਮੇਤ ਬਿਨਾਂ ਅਦਾਇਗੀ ਵਾਪਸ ਕਰ ਦਿੱਤਾ ਗਿਆ।\n\n2. ਅਨਾਦਰ ਦੀ ਸੂਚਨਾ ਦੇ ਤੀਹ ਦਿਨਾਂ ਦੇ ਅੰਦਰ ਮਿਤੀ {{noticeDate}} ਦਾ ਮੰਗ ਨੋਟਿਸ ਭੇਜਿਆ ਗਿਆ ਜੋ {{noticeServed}} ਨੂੰ ਤਾਮੀਲ ਹੋਇਆ। ਨੋਟਿਸ ਮਿਲਣ ਦੇ ਪੰਦਰਾਂ ਦਿਨਾਂ ਦੇ ਅੰਦਰ ਰਕਮ ਅਦਾ ਨਹੀਂ ਕੀਤੀ ਗਈ। ਸ਼ਿਕਾਇਤ {{complaintFiled}} ਨੂੰ, ਐਕਟ ਦੀ ਧਾਰਾ 142(1)(ਬੀ) ਅਨੁਸਾਰ ਕਾਰਨ ਪੈਦਾ ਹੋਣ ਦੇ ਇੱਕ ਮਹੀਨੇ ਦੇ ਅੰਦਰ, ਦਾਇਰ ਕੀਤੀ ਗਈ।\n\n3. ਐਕਟ ਦੀ ਧਾਰਾ 142(2) ਅਧੀਨ ਇਸ ਅਦਾਲਤ ਨੂੰ ਇਲਾਕਾਈ ਅਧਿਕਾਰ ਖੇਤਰ ਹੈ: {{jurisdiction}}\n\n4. ਮੁੱਢਲੀ ਗਵਾਹੀ (ਐਕਟ ਦੀ ਧਾਰਾ 145 ਅਧੀਨ ਹਲਫ਼ੀਆ ਬਿਆਨ ਰਾਹੀਂ): {{preliminaryEvidence}}\n\n5. ਧਾਰਾ 223(1) ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਦੇ ਪਰੰਤੁਕ ਅਨੁਸਾਰ ਸੰਗਿਆਨ ਤੋਂ ਪਹਿਲਾਂ ਮੁਲਜ਼ਮ ਨੂੰ ਸੁਣਵਾਈ ਦਾ ਮੌਕਾ ਦਿੱਤਾ ਗਿਆ: {{accusedHeard}}\n\n6. ਮਿਸਲ ਤੋਂ ਮੁੱਢਲੀ ਨਜ਼ਰੇ ਨੈਗੋਸ਼ੀਏਬਲ ਇੰਸਟਰੂਮੈਂਟਸ ਐਕਟ, 1881 ਦੀ ਧਾਰਾ 138 ਦੇ ਜੁਰਮ ਦੇ ਤੱਤ ਪ੍ਰਗਟ ਹੁੰਦੇ ਹਨ। ਸੰਗਿਆਨ ਲਿਆ ਜਾਂਦਾ ਹੈ। ਪ੍ਰੋਸੈਸ ਫ਼ੀਸ ਦਾਇਰ ਹੋਣ ਉੱਤੇ ਮੁਲਜ਼ਮ {{secondParty}} ਨੂੰ ਆਮ ਤਰੀਕੇ ਅਤੇ ਪਤਾ ਉਪਲਬਧ ਹੋਣ ਉੱਤੇ ਈ-ਮੇਲ / ਇਲੈਕਟ੍ਰਾਨਿਕ ਸਾਧਨਾਂ ਰਾਹੀਂ ਵੀ {{nextDate}} ਲਈ ਸੰਮਨ ਕੀਤਾ ਜਾਵੇ।',
    }),

  order('judicial-issues', 'checklist', 'civil',
    t('Framing of issues', 'वाद बिन्दुओं की विरचना', 'ਮੁੱਦੇ ਤੈਅ ਕਰਨਾ'),
    t('Order XIV CPC: issues with onus, and the next date for evidence.', 'आदेश 14 सी.पी.सी.: भार सबूत सहित वाद बिन्दु और साक्ष्य हेतु अगली तारीख।', 'ਆਰਡਰ 14 ਸੀ.ਪੀ.ਸੀ.: ਸਬੂਤ ਦੇ ਭਾਰ ਸਹਿਤ ਮੁੱਦੇ ਅਤੇ ਗਵਾਹੀ ਲਈ ਅਗਲੀ ਤਾਰੀਖ਼।'),
    t('Order: framing of issues (Order XIV Rule 1 CPC)', 'आदेश: वाद बिन्दुओं की विरचना (आदेश 14 नियम 1 सी.पी.सी.)', 'ਹੁਕਮ: ਮੁੱਦੇ ਤੈਅ ਕਰਨਾ (ਆਰਡਰ 14 ਰੂਲ 1 ਸੀ.ਪੀ.ਸੀ.)'),
    ['appearances', 'plaintCase', 'defence', 'issues', 'nextDate'],
    ['issues', 'order xiv', 'cpc', 'onus', 'civil suit'],
    {
      en: 'Present: {{appearances}}\n\n1. Pleadings are complete. The plaintiff’s case in brief: {{plaintCase}}\n\n2. The defendant’s case in brief: {{defence}}\n\n3. From the pleadings of the parties, the following issues are framed:\n{{issues}}\n\n4. No other issue arises or was pressed.\n\n5. To come up on {{nextDate}} for the plaintiff’s evidence. The parties shall file their lists of witnesses within fifteen days under Order XVI Rule 1 CPC.',
      hi: 'उपस्थित: {{appearances}}\n\n1. अभिवचन पूर्ण हैं। संक्षेप में वादी का कथन: {{plaintCase}}\n\n2. संक्षेप में प्रतिवादी का कथन: {{defence}}\n\n3. पक्षकारों के अभिवचनों के आधार पर निम्नलिखित वाद बिन्दु विरचित किए जाते हैं:\n{{issues}}\n\n4. अन्य कोई वाद बिन्दु उत्पन्न नहीं होता और न ही बल दिया गया।\n\n5. पत्रावली दिनांक {{nextDate}} को वादी के साक्ष्य हेतु पेश हो। पक्षकार आदेश 16 नियम 1 सी.पी.सी. के अंतर्गत पंद्रह दिन के भीतर साक्षियों की सूची प्रस्तुत करें।',
      pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n1. ਅਭਿਵਚਨ ਮੁਕੰਮਲ ਹਨ। ਸੰਖੇਪ ਵਿੱਚ ਮੁਦਈ ਦਾ ਕੇਸ: {{plaintCase}}\n\n2. ਸੰਖੇਪ ਵਿੱਚ ਮੁਦਾਲੇ ਦਾ ਕੇਸ: {{defence}}\n\n3. ਧਿਰਾਂ ਦੇ ਅਭਿਵਚਨਾਂ ਤੋਂ ਹੇਠ ਲਿਖੇ ਮੁੱਦੇ ਤੈਅ ਕੀਤੇ ਜਾਂਦੇ ਹਨ:\n{{issues}}\n\n4. ਕੋਈ ਹੋਰ ਮੁੱਦਾ ਨਾ ਪੈਦਾ ਹੁੰਦਾ ਹੈ ਅਤੇ ਨਾ ਹੀ ਉਸ ਉੱਤੇ ਜ਼ੋਰ ਦਿੱਤਾ ਗਿਆ।\n\n5. ਮਿਸਲ {{nextDate}} ਨੂੰ ਮੁਦਈ ਦੀ ਗਵਾਹੀ ਲਈ ਪੇਸ਼ ਹੋਵੇ। ਧਿਰਾਂ ਆਰਡਰ 16 ਰੂਲ 1 ਸੀ.ਪੀ.ਸੀ. ਅਧੀਨ ਪੰਦਰਾਂ ਦਿਨਾਂ ਦੇ ਅੰਦਰ ਆਪਣੇ ਗਵਾਹਾਂ ਦੀਆਂ ਸੂਚੀਆਂ ਦਾਇਰ ਕਰਨ।',
    },
    { defaults: { issues: ISSUES } }),

  order('judicial-temporary-injunction', 'block', 'civil',
    t('Temporary injunction order', 'अस्थायी निषेधाज्ञा आदेश', 'ਆਰਜ਼ੀ ਹੁਕਮ ਇਮਤਨਾਈ'),
    t('Order XXXIX Rules 1 and 2 CPC: prima facie case, balance of convenience, irreparable injury.', 'आदेश 39 नियम 1 व 2 सी.पी.सी.: प्रथम दृष्टया मामला, सुविधा का संतुलन, अपूरणीय क्षति।', 'ਆਰਡਰ 39 ਰੂਲ 1 ਅਤੇ 2 ਸੀ.ਪੀ.ਸੀ.: ਮੁੱਢਲੀ ਨਜ਼ਰੇ ਕੇਸ, ਸਹੂਲਤ ਦਾ ਸੰਤੁਲਨ, ਨਾ-ਪੂਰਨਯੋਗ ਨੁਕਸਾਨ।'),
    t('Order on application under Order XXXIX Rules 1 and 2 read with Section 151 CPC', 'आदेश 39 नियम 1 व 2 सपठित धारा 151 सी.पी.सी. के अंतर्गत प्रार्थना पत्र पर आदेश', 'ਆਰਡਰ 39 ਰੂਲ 1 ਅਤੇ 2 ਸਹਿਤ ਧਾਰਾ 151 ਸੀ.ਪੀ.ਸੀ. ਅਧੀਨ ਦਰਖ਼ਾਸਤ ਉੱਤੇ ਹੁਕਮ'),
    ['appearances', 'plaintCase', 'defence', 'primaFacie', 'balance', 'irreparable', 'operative'],
    ['temporary injunction', 'order xxxix', 'stay', 'status quo', 'cpc'],
    {
      en: 'Present: {{appearances}}\n\n1. By this order, the application of the plaintiff under Order XXXIX Rules 1 and 2 read with Section 151 CPC for the grant of a temporary injunction is being disposed of.\n\n2. Case of the plaintiff: {{plaintCase}}\n\n3. Reply of the defendant: {{defence}}\n\n4. I have heard learned counsel for the parties and perused the record. To be entitled to a temporary injunction, the plaintiff must show a prima facie case, that the balance of convenience lies in his/her favour, and that he/she would suffer irreparable injury if the injunction is refused (Dalpat Kumar v. Prahlad Singh, (1992) 1 SCC 719).\n\n5. Prima facie case: {{primaFacie}}\n\n6. Balance of convenience: {{balance}}\n\n7. Irreparable injury: {{irreparable}}\n\n8. {{operative}}\n\n9. The observations made herein are tentative, for the disposal of this application only, and shall have no bearing on the merits of the suit.',
      hi: 'उपस्थित: {{appearances}}\n\n1. इस आदेश द्वारा वादी के आदेश 39 नियम 1 व 2 सपठित धारा 151 सी.पी.सी. के अंतर्गत अस्थायी निषेधाज्ञा हेतु प्रस्तुत प्रार्थना पत्र का निस्तारण किया जा रहा है।\n\n2. वादी का कथन: {{plaintCase}}\n\n3. प्रतिवादी का उत्तर: {{defence}}\n\n4. मैंने पक्षकारों के विद्वान अधिवक्तागण को सुना तथा पत्रावली का अवलोकन किया। अस्थायी निषेधाज्ञा हेतु वादी को प्रथम दृष्टया मामला, अपने पक्ष में सुविधा का संतुलन तथा निषेधाज्ञा न दिए जाने पर अपूरणीय क्षति दर्शित करनी होती है (दलपत कुमार बनाम प्रहलाद सिंह, (1992) 1 एस.सी.सी. 719)।\n\n5. प्रथम दृष्टया मामला: {{primaFacie}}\n\n6. सुविधा का संतुलन: {{balance}}\n\n7. अपूरणीय क्षति: {{irreparable}}\n\n8. {{operative}}\n\n9. इस आदेश में की गई टिप्पणियाँ अस्थायी हैं, केवल इस प्रार्थना पत्र के निस्तारण हेतु हैं तथा वाद के गुण-दोष पर इनका कोई प्रभाव नहीं होगा।',
      pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n1. ਇਸ ਹੁਕਮ ਰਾਹੀਂ ਮੁਦਈ ਦੀ ਆਰਡਰ 39 ਰੂਲ 1 ਅਤੇ 2 ਸਹਿਤ ਧਾਰਾ 151 ਸੀ.ਪੀ.ਸੀ. ਅਧੀਨ ਆਰਜ਼ੀ ਹੁਕਮ ਇਮਤਨਾਈ ਲਈ ਦਰਖ਼ਾਸਤ ਦਾ ਨਿਪਟਾਰਾ ਕੀਤਾ ਜਾ ਰਿਹਾ ਹੈ।\n\n2. ਮੁਦਈ ਦਾ ਕੇਸ: {{plaintCase}}\n\n3. ਮੁਦਾਲੇ ਦਾ ਜਵਾਬ: {{defence}}\n\n4. ਮੈਂ ਧਿਰਾਂ ਦੇ ਵਿਦਵਾਨ ਵਕੀਲਾਂ ਨੂੰ ਸੁਣਿਆ ਅਤੇ ਮਿਸਲ ਦਾ ਅਧਿਐਨ ਕੀਤਾ। ਆਰਜ਼ੀ ਹੁਕਮ ਇਮਤਨਾਈ ਲਈ ਮੁਦਈ ਨੂੰ ਮੁੱਢਲੀ ਨਜ਼ਰੇ ਕੇਸ, ਆਪਣੇ ਪੱਖ ਵਿੱਚ ਸਹੂਲਤ ਦਾ ਸੰਤੁਲਨ ਅਤੇ ਹੁਕਮ ਇਮਤਨਾਈ ਨਾ ਮਿਲਣ ਉੱਤੇ ਨਾ-ਪੂਰਨਯੋਗ ਨੁਕਸਾਨ ਦਰਸਾਉਣਾ ਹੁੰਦਾ ਹੈ (ਦਲਪਤ ਕੁਮਾਰ ਬਨਾਮ ਪ੍ਰਹਿਲਾਦ ਸਿੰਘ, (1992) 1 ਐਸ.ਸੀ.ਸੀ. 719)।\n\n5. ਮੁੱਢਲੀ ਨਜ਼ਰੇ ਕੇਸ: {{primaFacie}}\n\n6. ਸਹੂਲਤ ਦਾ ਸੰਤੁਲਨ: {{balance}}\n\n7. ਨਾ-ਪੂਰਨਯੋਗ ਨੁਕਸਾਨ: {{irreparable}}\n\n8. {{operative}}\n\n9. ਇਸ ਹੁਕਮ ਵਿੱਚ ਕੀਤੀਆਂ ਟਿੱਪਣੀਆਂ ਆਰਜ਼ੀ ਹਨ, ਸਿਰਫ਼ ਇਸ ਦਰਖ਼ਾਸਤ ਦੇ ਨਿਪਟਾਰੇ ਲਈ ਹਨ ਅਤੇ ਦਾਵੇ ਦੀ ਮੈਰਿਟ ਉੱਤੇ ਇਨ੍ਹਾਂ ਦਾ ਕੋਈ ਅਸਰ ਨਹੀਂ ਹੋਵੇਗਾ।',
    }),

  order('judicial-decree-sheet', 'request_quote', 'civil',
    t('Decree sheet', 'डिक्री पत्र', 'ਡਿਕਰੀ ਸ਼ੀਟ'),
    t('Order XX Rules 6 and 6A CPC: particulars of the suit, terms of the decree and the costs table.', 'आदेश 20 नियम 6 व 6क सी.पी.सी.: वाद का विवरण, डिक्री की शर्तें और वाद व्यय तालिका।', 'ਆਰਡਰ 20 ਰੂਲ 6 ਅਤੇ 6ਏ ਸੀ.ਪੀ.ਸੀ.: ਦਾਵੇ ਦਾ ਵੇਰਵਾ, ਡਿਕਰੀ ਦੀਆਂ ਸ਼ਰਤਾਂ ਅਤੇ ਖ਼ਰਚੇ ਦੀ ਸਾਰਣੀ।'),
    t('Decree (Order XX Rules 6 and 6A CPC)', 'डिक्री (आदेश 20 नियम 6 व 6क सी.पी.सी.)', 'ਡਿਕਰੀ (ਆਰਡਰ 20 ਰੂਲ 6 ਅਤੇ 6ਏ ਸੀ.ਪੀ.ਸੀ.)'),
    ['suitNature', 'claim', 'appearances', 'decreeTerms', 'costs'],
    ['decree', 'decree sheet', 'order xx', 'costs', 'civil suit'],
    {
      en: 'Suit for {{suitNature}}\nClaim: {{claim}}\n\nThis suit coming on this day, {{orderDate}}, for final disposal before me, in the presence of {{appearances}}, it is ordered and decreed that:\n\n{{decreeTerms}}\n\nCosts of the suit:\n{{costs}}\n\nGiven under my hand and the seal of the court this day, {{orderDate}}.',
      hi: 'वाद: {{suitNature}}\nदावा: {{claim}}\n\nयह वाद आज दिनांक {{orderDate}} को {{appearances}} की उपस्थिति में मेरे समक्ष अंतिम निस्तारण हेतु प्रस्तुत होने पर आदेशित एवं आज्ञप्त किया जाता है कि:\n\n{{decreeTerms}}\n\nवाद व्यय:\n{{costs}}\n\nआज दिनांक {{orderDate}} को मेरे हस्ताक्षर एवं न्यायालय की मुहर से जारी।',
      pa: 'ਦਾਵਾ: {{suitNature}}\nਮੰਗ: {{claim}}\n\nਇਹ ਦਾਵਾ ਅੱਜ ਮਿਤੀ {{orderDate}} ਨੂੰ {{appearances}} ਦੀ ਹਾਜ਼ਰੀ ਵਿੱਚ ਮੇਰੇ ਸਾਹਮਣੇ ਅੰਤਿਮ ਨਿਪਟਾਰੇ ਲਈ ਪੇਸ਼ ਹੋਣ ਉੱਤੇ ਹੁਕਮ ਅਤੇ ਡਿਕਰੀ ਕੀਤਾ ਜਾਂਦਾ ਹੈ ਕਿ:\n\n{{decreeTerms}}\n\nਦਾਵੇ ਦਾ ਖ਼ਰਚਾ:\n{{costs}}\n\nਅੱਜ ਮਿਤੀ {{orderDate}} ਨੂੰ ਮੇਰੇ ਦਸਤਖ਼ਤ ਅਤੇ ਅਦਾਲਤ ਦੀ ਮੋਹਰ ਹੇਠ ਜਾਰੀ।',
    },
    { defaults: { costs: COSTS } }),

  order('judicial-maintenance', 'diversity_1', 'family',
    t('Maintenance order (interim / final)', 'भरण-पोषण आदेश (अंतरिम / अंतिम)', 'ਗੁਜ਼ਾਰਾ ਭੱਤੇ ਦਾ ਹੁਕਮ (ਅੰਤਰਿਮ / ਅੰਤਿਮ)'),
    t('Section 144 BNSS: affidavits of assets (Rajnesh v. Neha), income, needs and the monthly amount.', 'धारा 144 बी.एन.एस.एस.: आस्तियों के शपथपत्र (रजनेश बनाम नेहा), आय, आवश्यकताएँ और मासिक राशि।', 'ਧਾਰਾ 144 ਬੀ.ਐਨ.ਐਸ.ਐਸ.: ਜਾਇਦਾਦ ਦੇ ਹਲਫ਼ੀਆ ਬਿਆਨ (ਰਜਨੇਸ਼ ਬਨਾਮ ਨੇਹਾ), ਆਮਦਨ, ਲੋੜਾਂ ਅਤੇ ਮਹੀਨਾਵਾਰ ਰਕਮ।'),
    t('Order on application for maintenance under Section 144 BNSS', 'धारा 144 बी.एन.एस.एस. के अंतर्गत भरण-पोषण प्रार्थना पत्र पर आदेश', 'ਧਾਰਾ 144 ਬੀ.ਐਨ.ਐਸ.ਐਸ. ਅਧੀਨ ਗੁਜ਼ਾਰਾ ਭੱਤੇ ਦੀ ਦਰਖ਼ਾਸਤ ਉੱਤੇ ਹੁਕਮ'),
    ['appearances', 'applicantCase', 'respondentCase', 'affidavitsFiled', 'incomeFindings', 'reasons', 'amount', 'effectiveFrom'],
    ['maintenance', 'bnss 144', 'section 125', 'interim maintenance', 'family court', 'rajnesh'],
    {
      en: 'Present: {{appearances}}\n\n1. This order disposes of the application of {{firstParty}} for [interim] maintenance under Section 144 of the Bharatiya Nagarik Suraksha Sanhita, 2023 against the respondent {{secondParty}}.\n\n2. Case of the applicant(s): {{applicantCase}}\n\n3. Case of the respondent: {{respondentCase}}\n\n4. Both parties have filed affidavits of disclosure of assets and liabilities in the format prescribed in Rajnesh v. Neha, (2021) 2 SCC 324: {{affidavitsFiled}}\n\n5. Income, status and reasonable needs of the parties: {{incomeFindings}}\n\n6. {{reasons}}\n\n7. Accordingly, the respondent {{secondParty}} is directed to pay maintenance of Rs. {{amount}} per month to {{firstParty}} with effect from {{effectiveFrom}}, payable by the 10th of each month. Arrears, if any, shall be paid within [__] months. [Interim maintenance shall be adjusted in the final order.]',
      hi: 'उपस्थित: {{appearances}}\n\n1. इस आदेश द्वारा {{firstParty}} के भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 144 के अंतर्गत विपक्षी {{secondParty}} के विरुद्ध [अंतरिम] भरण-पोषण हेतु प्रार्थना पत्र का निस्तारण किया जा रहा है।\n\n2. आवेदक(गण) का कथन: {{applicantCase}}\n\n3. विपक्षी का कथन: {{respondentCase}}\n\n4. उभय पक्ष ने रजनेश बनाम नेहा, (2021) 2 एस.सी.सी. 324 में निर्धारित प्रारूप में आस्तियों एवं दायित्वों के प्रकटीकरण के शपथपत्र प्रस्तुत किए हैं: {{affidavitsFiled}}\n\n5. पक्षकारों की आय, स्थिति एवं युक्तियुक्त आवश्यकताएँ: {{incomeFindings}}\n\n6. {{reasons}}\n\n7. अतः विपक्षी {{secondParty}} को निर्देशित किया जाता है कि वह {{firstParty}} को दिनांक {{effectiveFrom}} से रु. {{amount}} प्रतिमाह भरण-पोषण प्रत्येक माह की 10 तारीख तक अदा करे। बकाया राशि, यदि कोई हो, [__] माह के भीतर अदा की जाए। [अंतरिम भरण-पोषण अंतिम आदेश में समायोजित होगा।]',
      pa: 'ਹਾਜ਼ਰ: {{appearances}}\n\n1. ਇਸ ਹੁਕਮ ਰਾਹੀਂ {{firstParty}} ਦੀ ਭਾਰਤੀ ਨਾਗਰਿਕ ਸੁਰੱਖਿਆ ਸੰਹਿਤਾ, 2023 ਦੀ ਧਾਰਾ 144 ਅਧੀਨ ਜਵਾਬਦੇਹ {{secondParty}} ਵਿਰੁੱਧ [ਅੰਤਰਿਮ] ਗੁਜ਼ਾਰਾ ਭੱਤੇ ਦੀ ਦਰਖ਼ਾਸਤ ਦਾ ਨਿਪਟਾਰਾ ਕੀਤਾ ਜਾਂਦਾ ਹੈ।\n\n2. ਬਿਨੈਕਾਰ(ਾਂ) ਦਾ ਕੇਸ: {{applicantCase}}\n\n3. ਜਵਾਬਦੇਹ ਦਾ ਕੇਸ: {{respondentCase}}\n\n4. ਦੋਹਾਂ ਧਿਰਾਂ ਨੇ ਰਜਨੇਸ਼ ਬਨਾਮ ਨੇਹਾ, (2021) 2 ਐਸ.ਸੀ.ਸੀ. 324 ਵਿੱਚ ਨਿਰਧਾਰਤ ਫ਼ਾਰਮੈਟ ਵਿੱਚ ਜਾਇਦਾਦ ਅਤੇ ਦੇਣਦਾਰੀਆਂ ਦੇ ਖੁਲਾਸੇ ਦੇ ਹਲਫ਼ੀਆ ਬਿਆਨ ਦਾਇਰ ਕੀਤੇ ਹਨ: {{affidavitsFiled}}\n\n5. ਧਿਰਾਂ ਦੀ ਆਮਦਨ, ਹਾਲਤ ਅਤੇ ਵਾਜਬ ਲੋੜਾਂ: {{incomeFindings}}\n\n6. {{reasons}}\n\n7. ਇਸ ਲਈ ਜਵਾਬਦੇਹ {{secondParty}} ਨੂੰ ਹਦਾਇਤ ਕੀਤੀ ਜਾਂਦੀ ਹੈ ਕਿ ਉਹ {{firstParty}} ਨੂੰ {{effectiveFrom}} ਤੋਂ {{amount}} ਰੁਪਏ ਪ੍ਰਤੀ ਮਹੀਨਾ ਗੁਜ਼ਾਰਾ ਭੱਤਾ ਹਰ ਮਹੀਨੇ ਦੀ 10 ਤਾਰੀਖ਼ ਤੱਕ ਅਦਾ ਕਰੇ। ਬਕਾਇਆ, ਜੇ ਕੋਈ ਹੋਵੇ, [__] ਮਹੀਨਿਆਂ ਦੇ ਅੰਦਰ ਅਦਾ ਕੀਤਾ ਜਾਵੇ। [ਅੰਤਰਿਮ ਗੁਜ਼ਾਰਾ ਭੱਤਾ ਅੰਤਿਮ ਹੁਕਮ ਵਿੱਚ ਸਮਾਯੋਜਿਤ ਕੀਤਾ ਜਾਵੇਗਾ।]',
    }),
];

/** The words of the frame in each drafting language. */
const WORDS = {
  en: {
    inTheCourtOf: 'IN THE COURT OF', courtColon: 'IN THE COURT OF', presiding: 'Presiding Officer', jo: 'JO Code', uid: 'UID No.',
    cnr: 'CNR No.', versus: 'Versus', orderDated: 'Order dated', dated: 'Dated', ps: 'Police Station', under: 'under',
    firAllahabad: 'Case Crime No. / FIR No.', fir: 'FIR No.', hp: 'H.P.',
    announced: (d: string) => `Announced in open court.\nDated: ${d}\n\n`,
    announcedOn: (d: string) => `Announced in the open court on ${d}.\n\n`,
    announcedToday: (d: string) => `Announced in open court today, ${d}.\n\n`,
    pronounced: 'Judgment signed, dated and pronounced by me in open court today.\n\n',
    pageNote: '\n\nNote: All the pages of this judgment have been checked and signed by me.',
  },
  hi: {
    inTheCourtOf: 'न्यायालय', courtColon: 'न्यायालय:', presiding: 'पीठासीन अधिकारी', jo: 'जे.ओ. कोड', uid: 'यू.आई.डी. नं.',
    cnr: 'सी.एन.आर. सं.', versus: 'बनाम', orderDated: 'आदेश दिनांक', dated: 'दिनांक', ps: 'थाना', under: 'धारा',
    firAllahabad: 'मु.अ.सं.', fir: 'एफ.आई.आर. नं.', hp: 'हि.प्र.',
    announced: (d: string) => `खुले न्यायालय में उद्घोषित।\nदिनांक: ${d}\n\n`,
    announcedOn: (d: string) => `खुले न्यायालय में दिनांक ${d} को उद्घोषित।\n\n`,
    announcedToday: (d: string) => `आज दिनांक ${d} को खुले न्यायालय में उद्घोषित।\n\n`,
    pronounced: 'आज यह निर्णय मेरे द्वारा खुले न्यायालय में हस्ताक्षरित, दिनांकित कर उद्घोषित किया गया।\n\n',
    pageNote: '\n\nनोट: इस निर्णय के सभी पृष्ठ मेरे द्वारा जाँच कर हस्ताक्षरित किए गए हैं।',
  },
  pa: {
    inTheCourtOf: 'ਅਦਾਲਤ', courtColon: 'ਅਦਾਲਤ:', presiding: 'ਪੀਠਾਸੀਨ ਅਧਿਕਾਰੀ', jo: 'ਜੇ.ਓ. ਕੋਡ', uid: 'ਯੂ.ਆਈ.ਡੀ. ਨੰ.',
    cnr: 'ਸੀ.ਐਨ.ਆਰ. ਨੰ.', versus: 'ਬਨਾਮ', orderDated: 'ਹੁਕਮ ਮਿਤੀ', dated: 'ਮਿਤੀ', ps: 'ਥਾਣਾ', under: 'ਧਾਰਾ',
    firAllahabad: 'ਮੁਕੱਦਮਾ ਨੰ. / ਐਫ.ਆਈ.ਆਰ. ਨੰ.', fir: 'ਐਫ.ਆਈ.ਆਰ. ਨੰ.', hp: 'ਹਿ.ਪ੍ਰ.',
    announced: (d: string) => `ਖੁੱਲ੍ਹੀ ਅਦਾਲਤ ਵਿੱਚ ਸੁਣਾਇਆ ਗਿਆ।\nਮਿਤੀ: ${d}\n\n`,
    announcedOn: (d: string) => `ਖੁੱਲ੍ਹੀ ਅਦਾਲਤ ਵਿੱਚ ਮਿਤੀ ${d} ਨੂੰ ਸੁਣਾਇਆ ਗਿਆ।\n\n`,
    announcedToday: (d: string) => `ਅੱਜ ਮਿਤੀ ${d} ਨੂੰ ਖੁੱਲ੍ਹੀ ਅਦਾਲਤ ਵਿੱਚ ਸੁਣਾਇਆ ਗਿਆ।\n\n`,
    pronounced: 'ਇਹ ਫ਼ੈਸਲਾ ਅੱਜ ਮੇਰੇ ਦੁਆਰਾ ਖੁੱਲ੍ਹੀ ਅਦਾਲਤ ਵਿੱਚ ਦਸਤਖ਼ਤ ਕਰ ਕੇ, ਮਿਤੀ ਪਾ ਕੇ ਸੁਣਾਇਆ ਗਿਆ।\n\n',
    pageNote: '\n\nਨੋਟ: ਇਸ ਫ਼ੈਸਲੇ ਦੇ ਸਾਰੇ ਪੰਨੇ ਮੇਰੇ ਦੁਆਰਾ ਜਾਂਚ ਕੇ ਦਸਤਖ਼ਤ ਕੀਤੇ ਗਏ ਹਨ।',
  },
} as const;

/** Words that change with the state: heading, FIR line, signature, judgment close. */
function frame(state: OrderState, language: DraftLanguage, v: (key: string) => string, judgment: boolean) {
  const w = WORDS[language];
  const en = language === 'en';
  const style = STYLE[state];
  const officer = `${v('judgeName')}, ${v('judgeDesignation')}`;
  let heading: string;
  switch (style) {
    case 'allahabad':
      heading = en
        ? `IN THE COURT OF ${v('court')}, ${v('place')}\nPresiding Officer: ${officer}\nJO Code: ${v('officerCode')}`
        : `${w.courtColon} ${v('court')}, ${v('place')}\n${w.presiding}: ${officer}\n${w.jo}: ${v('officerCode')}`;
      break;
    case 'ph':
      heading = `${w.inTheCourtOf} ${officer}, ${v('place')}\n${w.uid} ${v('officerCode')}`;
      break;
    case 'delhi':
      heading = `${w.inTheCourtOf} ${officer}\n${v('court')}, ${v('place')}`;
      break;
    case 'hp':
      heading = `${w.inTheCourtOf} ${officer}, ${v('place')}, ${w.hp}`;
      break;
    default:
      heading = `${v('court')}\n${v('place')}`;
  }
  const fir = style === 'allahabad' ? w.firAllahabad : w.fir;
  const firLine = `${fir} ${v('firNumber')}, ${w.ps} ${v('policeStation')}, ${w.under} ${v('sections')}`;
  let close = '';
  if (judgment) {
    close = style === 'allahabad' ? w.pronounced
      : style === 'delhi' ? w.announcedOn(v('orderDate'))
        : style === 'hp' ? w.announcedToday(v('orderDate'))
          : w.announced(v('orderDate'));
  }
  let sign: string;
  switch (style) {
    case 'allahabad':
      sign = `(${v('judgeName')})\n${v('court')}, ${v('place')}\n${w.jo}: ${v('officerCode')}\n${w.dated}: ${v('orderDate')}`;
      break;
    case 'ph':
      sign = `(${v('judgeName')})\n${v('judgeDesignation')}, ${v('place')}\n${w.uid} ${v('officerCode')}\n${v('orderDate')}`;
      break;
    case 'delhi':
      sign = `(${v('judgeName')})\n${v('judgeDesignation')}\n${v('court')}, ${v('place')}\n${w.dated}: ${v('orderDate')}`;
      break;
    case 'hp':
      sign = `(${v('judgeName')})\n${v('judgeDesignation')},\n${v('place')}, ${w.hp}\n${w.dated}: ${v('orderDate')}`;
      break;
    default:
      sign = `____________________________\n${v('judgeName')}\n${v('judgeDesignation')}\n${v('court')}`;
  }
  const pageNote = judgment && style === 'ph' ? w.pageNote : '';
  return { heading, firLine, close, sign, pageNote };
}

/** The body text of a format in a language (Punjabi falls back to English). */
function bodyIn(format: OrderFormat, language: DraftLanguage): string {
  return language === 'hi' ? format.body.hi : language === 'pa' ? (format.body.pa ?? format.body.en) : format.body.en;
}

/** The finished order text. `labels` names unfilled fields ("[Bond amount (Rs.)]"). */
export function renderOrder(
  format: OrderFormat, language: DraftLanguage, state: OrderState,
  values: Record<string, string>, labels: Record<string, LocalText>,
): string {
  const w = WORDS[language];
  const v = (key: string) => values[key]?.trim() || `[${labels[key]?.[language] ?? key}]`;
  const f = frame(state, language, v, !!format.judgment);
  const has = (key: string) => format.fields.includes(key);
  const body = bodyIn(format, language).replace(/\{\{(\w+)\}\}/g, (_, key: string) => v(key));
  const caseBlock = [
    v('caseNumber'),
    `${w.cnr} ${v('cnr')}`,
    '',
    v('firstParty'),
    w.versus,
    v('secondParty'),
    ...(has('firNumber') ? ['', f.firLine] : []),
  ].join('\n');
  const title = language === 'en' ? format.purpose.en.toUpperCase() : format.purpose[language];
  const dated = format.judgment ? '' : `${w.orderDated}: ${v('orderDate')}\n\n`;
  return `${f.heading}\n\n${caseBlock}\n\n${title}\n\n${dated}${body}\n\n${f.close}${f.sign}${f.pageNote}`;
}

const STATE_PARTY: Record<Exclude<OrderState, 'general'>, Bilingual> = {
  up: { en: 'State of Uttar Pradesh', hi: 'उत्तर प्रदेश राज्य', pa: 'ਉੱਤਰ ਪ੍ਰਦੇਸ਼ ਰਾਜ' },
  uk: { en: 'State of Uttarakhand', hi: 'उत्तराखण्ड राज्य', pa: 'ਉੱਤਰਾਖੰਡ ਰਾਜ' },
  hr: { en: 'State of Haryana', hi: 'हरियाणा राज्य', pa: 'ਹਰਿਆਣਾ ਰਾਜ' },
  pb: { en: 'State of Punjab', hi: 'पंजाब राज्य', pa: 'ਪੰਜਾਬ ਰਾਜ' },
  dl: { en: 'State (NCT of Delhi)', hi: 'राज्य (रा.रा.क्षे. दिल्ली)', pa: 'ਰਾਜ (ਐਨ.ਸੀ.ਟੀ. ਦਿੱਲੀ)' },
  hp: { en: 'State of Himachal Pradesh', hi: 'हिमाचल प्रदेश राज्य', pa: 'ਹਿਮਾਚਲ ਪ੍ਰਦੇਸ਼ ਰਾਜ' },
};

const textIn = (text: Bilingual, language: DraftLanguage): string =>
  language === 'hi' ? text.hi : language === 'pa' ? (text.pa ?? text.en) : text.en;
const variants = (text: Bilingual): string[] => [text.en, text.hi, ...(text.pa ? [text.pa] : [])];

/** Standard wording for a format in a language and state, keeping anything the officer typed. */
export function withOrderDefaults(
  format: DraftTemplate, language: DraftLanguage, values: Record<string, string>, state: OrderState = 'general',
): Record<string, string> {
  if (!isOrderFormat(format)) return values;
  const defaults: Record<string, Bilingual> = { ...format.defaults };
  // Police cases are State v. accused (a Section 138 complaint is not).
  if (format.category === 'criminal' && format.id !== 'judicial-ni-138' && state !== 'general') defaults['firstParty'] = STATE_PARTY[state];
  const known = new Set(Object.values(STATE_PARTY).flatMap(variants));
  const next = { ...values };
  if (next['firstParty'] && known.has(next['firstParty'].trim()) && !defaults['firstParty']) next['firstParty'] = '';
  for (const [key, text] of Object.entries(defaults)) {
    const current = next[key]?.trim();
    if (!current || variants(text).includes(current) || (key === 'firstParty' && known.has(current))) next[key] = textIn(text, language);
  }
  return next;
}

export function isOrderFormat(template: DraftTemplate): template is OrderFormat {
  return 'body' in template;
}

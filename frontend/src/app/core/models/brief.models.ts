import { DailyCard, DirectoryPerson } from './network.models';

/** backend app/modules/brief/schemas.py */
export type BriefLead = 'section' | 'judgment' | 'quiz' | 'on_this_day' | 'news' | 'fraternity';

export interface QuizStats { answers: number; right: number; }

export interface BriefQuiz {
  id: string;
  topic: string;
  question: string;
  options: string[];
  link: string | null;
  /** Set only once this member has answered. */
  chosen: number | null;
  answer: number | null;
  explanation: string | null;
  stats: QuizStats;
}

export interface OnThisDay {
  case: string;
  decided: string;
  citation: string | null;
  holding: string;
  judgment_id: string | null;
  source: 'curated' | 'corpus';
}

export interface BriefFraternity {
  members: number;
  in_city: number;
  joined_7d: number;
  city: string | null;
  people: DirectoryPerson[];
}

export interface Brief {
  day: string;
  weekday: string;
  lead: BriefLead;
  section: DailyCard | null;
  judgment: DailyCard | null;
  news: DailyCard[];
  quiz: BriefQuiz | null;
  on_this_day: OnThisDay | null;
  fraternity: BriefFraternity | null;
}

export interface QuizAnswer {
  quiz_id: string;
  chosen: number;
  answer: number;
  correct: boolean;
  explanation: string;
  stats: QuizStats;
  answered_at: string;
}

export const LEAD_TITLES: Record<BriefLead, string> = {
  section: 'Section of the day',
  judgment: 'Judgment of the day',
  quiz: "Today's question",
  on_this_day: 'On this day',
  news: 'The week in law',
  fraternity: 'Your fraternity',
};

/** One line about the lead item, for the home screen card. */
export function briefTeaser(b: Brief): string {
  switch (b.lead) {
    case 'section': return b.section?.title ?? 'A section of the new codes, with its old-law number.';
    case 'judgment': return b.judgment?.title ?? 'A Supreme Court judgment, summarised.';
    case 'quiz': return b.quiz?.question ?? 'One question on the law. Answer in the app.';
    case 'on_this_day': return b.on_this_day ? `${b.on_this_day.case} (${b.on_this_day.decided.slice(0, 4)})` : 'A landmark decided on this date.';
    case 'news': return b.news.map((n) => n.title).slice(0, 2).join(' · ') || 'Legal news of the week.';
    case 'fraternity': return b.fraternity ? `${b.fraternity.joined_7d} joined this week${b.fraternity.city && b.fraternity.in_city ? `, ${b.fraternity.in_city} in ${b.fraternity.city}` : ''}.` : 'Who joined near you.';
  }
}

/** Legal research API contracts (mirrors the backend research module). */

export type CourtLevel = 'supreme_court' | 'high_court' | 'tribunal' | 'district' | 'other';
export type CitationRelationship =
  | 'followed' | 'overruled' | 'distinguished' | 'referred' | 'relied_on' | 'dissented';

export interface JudgmentSummary {
  id: string;
  case_name: string;
  /** Null for High Court order records — only reported judgments carry one. */
  citation: string | null;
  /** eCourts Case Number Record; how citation-less records are identified. */
  cnr_number: string | null;
  /** Parsed from the registry title, e.g. "CRM-M" / "33310" / 2019. */
  case_type: string | null;
  case_number: string | null;
  case_year: number | null;
  /** Title without the "TYPE/NUM/YEAR of" prefix; prefer over case_name. */
  cause_title: string | null;
  /** Normalised bare judge names — display with a "Justice" prefix. */
  judge_names: string[];
  court: string;
  court_level: CourtLevel;
  judgment_date: string | null;
  outcome: string | null;
  /** Registry filing date; with judgment_date gives how long the case ran. */
  filed_on: string | null;
  /** The two sides, split from the cause title. */
  petitioner: string | null;
  respondent: string | null;
  /** Counsel on record, where the registry prints it in the order's opening. */
  petitioner_advocates: string[];
  respondent_advocates: string[];
  /** Matched fragment with <mark> around hits (full-text search only). */
  snippet?: string | null;
  /** AI headnote summary (Supreme Court judgments that have one); shown labelled as AI. */
  ai_summary?: string | null;
  /** Orders the library holds for this row's case (CNR); null without a CNR. */
  order_count?: number | null;
}

/** One order in a case's timeline. */
export interface CaseOrder {
  id: string;
  judgment_date: string | null;
  judge_names: string[];
  outcome: string | null;
  url: string | null;
  /** The registry's opening line of the order. */
  summary: string | null;
}

/** A case (one CNR) with every order the library holds for it, oldest first. */
export interface CaseRead {
  cnr_number: string;
  court: string;
  court_level: CourtLevel;
  case_type: string | null;
  case_number: string | null;
  case_year: number | null;
  cause_title: string | null;
  petitioner: string | null;
  respondent: string | null;
  petitioner_advocates: string[];
  respondent_advocates: string[];
  judge_names: string[];
  filed_on: string | null;
  first_order_on: string | null;
  latest_order_on: string | null;
  latest_outcome: string | null;
  orders: CaseOrder[];
}

export interface SearchPage {
  items: JudgmentSummary[];
  total: number;
  /** True when `total` is a planner estimate for a very large match set. */
  total_is_estimate: boolean;
  /** True when `total` is a floor counted past — show "More than N". */
  total_is_lower_bound: boolean;
  page: number;
  size: number;
  /** False when too many matched to rank; results are newest-first instead. */
  ranked: boolean;
  /** When set, an unranked page was drawn from only the last N years. */
  recent_years: number | null;
}

export interface FacetBucket {
  value: string;
  count: number;
}

export interface SearchFacets {
  total: number;
  total_is_estimate: boolean;
  total_is_lower_bound: boolean;
  /** When set, the counts cover only the last N years (very broad queries). */
  recent_years: number | null;
  /** True when the aggregation timed out; buckets are empty but results work. */
  facets_partial: boolean;
  courts: FacetBucket[];
  years: FacetBucket[];
  case_types: FacetBucket[];
  judges: FacetBucket[];
  advocates: FacetBucket[];
  outcomes: FacetBucket[];
}

export interface Judgment extends JudgmentSummary {
  neutral_citation: string | null;
  bench: string | null;
  judges: string[];
  acts: string[];
  sections: string[];
  keywords: string[];
  headnote: string | null;
  url: string | null;
  /** Text extracted from the order PDF; null until extracted. */
  full_text: string | null;
  text_extracted_at: string | null;
  /** AI-written headnote (Supreme Court); always shown with its AI flag. */
  ai_headnote?: AiHeadnote | null;
  created_at: string;
}

export interface AiHeadnote {
  ai_generated: true;
  label: string;
  model: string | null;
  generated_at: string | null;
  version: string | null;
  summary: string;
  issues: string[];
  provisions: { act: string; provision: string; how_applied: string; paragraphs: string[] }[];
  held: { point: string; paragraphs: string[] }[];
  result: string;
}

export interface JudgmentCreate {
  case_name: string;
  citation: string;
  court: string;
  court_level?: CourtLevel;
  judges?: string[];
  judgment_date?: string | null;
  acts?: string[];
  sections?: string[];
  keywords?: string[];
  headnote?: string | null;
  outcome?: string | null;
}

export interface CitationEdge {
  id: string;
  relationship_type: CitationRelationship;
  judgment_id: string | null;
  case_name: string | null;
  citation: string;
}

export interface CitationGraph {
  cites: CitationEdge[];
  cited_by: CitationEdge[];
}

export interface SearchFilters {
  q?: string;
  court_level?: CourtLevel | '';
  court?: string;
  case_type?: string;
  case_year?: number | null;
  judge?: string;
  advocate?: string;
  outcome?: string;
  act?: string;
  section?: string;
  year_from?: number | null;
  year_to?: number | null;
}

/** The facet dimensions a user can click into. */
export type FacetKey = 'court' | 'case_year' | 'case_type' | 'judge' | 'advocate' | 'outcome';

// ── Cite check (POST /research/cite-check) ──────────────────────────────
export type CiteCheckStatus = 'verified' | 'matched_by_name' | 'possible_matches' | 'cited_elsewhere' | 'not_found';

export interface CiteCheckJudgment {
  id: string;
  case_name: string;
  citation: string | null;
  neutral_citation: string | null;
  court: string;
  judgment_date: string | null;
}

export interface CiteCheckFinding {
  /** Normalised, e.g. "(2019) 5 SCC 123" or "[2019] 4 S.C.R. 532". */
  citation: string;
  reporter: string;
  kind: 'scr' | 'insc' | 'neutral' | 'reporter';
  year: number;
  case_name_as_cited: string | null;
  occurrences: number;
  /** Up to three passages around the citation in the draft. */
  contexts: string[];
  status: CiteCheckStatus;
  judgment: CiteCheckJudgment | null;
  candidates: CiteCheckJudgment[];
  /** Judgments in the library whose text cites this string (capped at 50). */
  cited_in_count: number;
  cited_in_examples: CiteCheckJudgment[];
  warnings: string[];
}

export interface CiteCheckReport {
  source_chars: number;
  citations_found: number;
  distinct_citations: number;
  truncated: boolean;
  counts: Partial<Record<CiteCheckStatus, number>>;
  findings: CiteCheckFinding[];
  checked_at: string;
  note: string;
}

// Hand-maintained mirror of the backend Pydantic/SQLModel schemas.

export type Formality = 'casual' | 'smart casual' | 'business' | 'formal';
export type ApiSource = 'live' | 'replay' | 'mock' | 'rule' | 'local';

export interface WardrobeItem {
  id: string;
  name: string;
  category: string;
  subcategory: string;
  color: string | null;
  style: string | null;
  brand: string | null;
  season: string | null;
  material: string | null;
  formality: Formality | string;
  waterproof: boolean;
  image_url: string;
  last_worn: string | null;
  number_of_times_worn: number;
  is_favorite: boolean;
  source: string;
  scan_meta: Record<string, unknown> | null;
  created_at: string;
}

export interface Scores {
  overall: number;
  vibe: number;
  dress_code: number;
  weather: number;
  color: number;
  freshness: number;
}

export interface OutfitPick {
  item_ids: string[];
  scores: Scores;
  rationale: string;
  ref?: string | null;
}

export interface PlanEvent {
  name: string;
  time?: string | null;
  dress_code?: string | null;
  outfit: OutfitPick | null;
  alternates: OutfitPick[];
}

export interface DayWeather {
  high_f: number | null;
  low_f: number | null;
  precip_pct: number | null;
  summary?: string | null;
}

export interface PlanDay {
  date: string;
  weather: DayWeather | null;
  events: PlanEvent[];
}

export interface SecondhandSuggestion {
  description: string;
  why: string;
  links: { site: string; url: string }[];
}

export interface Gap {
  need: string;
  severity: 'must-have' | 'nice-to-have' | string;
  reason: string;
  suggestion: SecondhandSuggestion | null;
}

export interface Plan {
  trip: { city: string; start: string; end: string; summary: string };
  days: PlanDay[];
  packing_list: { item_id: string; used_on: string[] }[];
  gaps: Gap[];
  notes?: string[];
}

export type StepKind =
  | 'input'
  | 'thinking'
  | 'tool_call'
  | 'decision'
  | 'message'
  | 'validation'
  | 'fallback'
  | 'error'
  | 'final';

export interface TraceStep {
  id: string;
  kind: StepKind;
  tool?: string | null;
  title: string;
  detail?: string | null;
  args?: unknown;
  result?: unknown;
  source?: ApiSource | null;
  started_at: string;
  duration_ms?: number | null;
  status: 'running' | 'done' | 'error';
  decision?: {
    winner_scores?: Scores;
    candidates_scored?: number;
    questions?: number;
  } | null;
}

export interface AgentRun {
  id: string;
  message: string;
  status: 'running' | 'completed' | 'failed' | 'needs_input';
  plan: Plan | null;
  trace: TraceStep[];
  sources: Record<string, string>;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface Health {
  status: string;
  agents_mode: string;
  decisions_mode: string;
  key_configured?: boolean;
  vision_configured?: boolean;
  calendar?: string;
  home_city?: string;
}

export interface DeviceLocation {
  lat: number;
  lon: number;
  city: string;
  label: string;
}

export interface PreflightCheck {
  ok: boolean;
  ms?: number;
  error?: string;
}

export interface Preflight {
  key_configured: boolean;
  modes: { agents: string; decisions: string };
  recordings: { agents: number; decisions: number };
  vision_configured: boolean;
  decisions: PreflightCheck;
  agents: PreflightCheck;
}

export interface CalendarEvent {
  id: string;
  date: string;
  start_time: string | null;
  name: string;
  location: string;
  dress_code_hint: string | null;
  calendar?: 'real';
}

export interface CalendarResponse {
  source: 'google' | 'ics' | 'none';
  label: string;
  note: string | null;
  events: CalendarEvent[];
}

export interface GoogleCalendarStatus {
  configured: boolean;
  connected: boolean;
  email: string | null;
}

// ---------------------------------------------------------------------------
// Should I Buy This?
// ---------------------------------------------------------------------------
export type Verdict = 'great_buy' | 'maybe' | 'skip';

export interface BuyCheckItem {
  name: string;
  category: string;
  subcategory: string;
  color: string | null;
  style: string | null;
  brand: string | null;
  season: string | null;
  material: string | null;
  formality: Formality | string;
  waterproof: boolean;
  image_url: string;
}

export interface BuyCheckResult {
  score: number;
  verdict: Verdict;
  outfit_count: number;
  duplicates: { item_id: string; name: string; reason: string }[];
  gap_filled: string | null;
  calendar_matches: { event: string; date: string }[];
  est_wears_per_year: number;
  /** Each outfit includes the new item, with id "new". */
  top_outfits: { items: WardrobeItem[]; includes_new: boolean }[];
  score_reason: string;
}

export interface BuyCheckUsage {
  checks_used: number;
  limit: number;
  pro: boolean;
}

export interface BuyCheckResponse {
  check_id: string;
  item: BuyCheckItem;
  result: BuyCheckResult;
  trace: TraceStep[];
  usage: BuyCheckUsage;
}

/** Body of the 402 the API returns once the free checks are used up. */
export interface Paywall {
  paywall: 'buy_check';
  used: number;
  limit: number;
}

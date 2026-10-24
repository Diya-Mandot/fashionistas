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
  status: 'running' | 'completed' | 'failed';
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

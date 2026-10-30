export type Rect = [number, number, number, number]
export type Status = 'confirmed' | 'needs_review' | 'dismissed' | 'not_observable'
export const STATUSES: Status[] = ['confirmed', 'needs_review', 'dismissed', 'not_observable']

export interface Evidence {
  sam_fill: number | null
  sam_spill: number | null
  sam_conf: number | null
  sam_iou: number | null
  opacity_diff: number | null
  sam_boxes: [number, number, number, number, number][]
  observable: boolean
}

export interface Triage {
  verdict: 'real_defect' | 'intentional' | 'not_visible' | 'unsure'
  defect_type: string
  severity: number
  what_the_user_sees: string
  fix_hint: string
  confidence: number
}

export interface CandidateRef {
  type: string
  state_key: string
  tile: number
  elements: number[]
  metrics: Record<string, number>
}

export interface Finding {
  key: string
  type: string
  status: Status
  widths: number[]
  candidates: CandidateRef[]
  evidence: Evidence[]
  triage: Triage | null
  locs: string[]
}

export interface TileRef { index: number; sha: string; scroll_y: number }

export interface StateInfo {
  key: string
  route: string
  width: number
  height: number
  theme: string
  text_stress: string
  status: 'running' | 'captured' | 'done'
  vw?: number
  vh?: number
  doc_w?: number
  doc_h?: number
  tiles: TileRef[]
}

export interface ElementBox { id: number; tag: string; rect: Rect; loc: string | null; text: string }

export interface CandidateInfo {
  state_key: string
  idx: number
  defect: string
  tile: number
  metrics: Record<string, number>
  elements: ElementBox[]
  evidence?: Evidence
}

/** The per-state detail the API serves for the overlay (DOM elements are too many to ride on every event). */
export interface StateDetail {
  capture: { tiles: { scroll_y: number; png_sha: string; elements: (ElementBox & { parent: number | null })[] }[] }
}

export interface RunInfo {
  run_id: string
  target: string
  split: string | null
  routes: string[]
  states: number
  models: boolean
  mode: string
  budget_usd: number
  widths: number[]
  themes: string[]
  text_stress: string[]
  status: 'running' | 'done' | 'failed' | 'cancelled' | 'stopped'
  counts?: Record<string, number>
}

export interface Verification {
  target_gone: boolean
  new_findings: string[]
  drifted: string[]
  build_ok: boolean
  lint_ok: boolean
  grid: Record<string, boolean>
  shots: Record<string, string>
  notes: string[]
}

export interface TimelineRow {
  id: number
  name: string
  args: Record<string, unknown>
  status: 'running' | 'ok' | 'fail' | 'blocked'
  detail: string
}

export interface Patch { diff: string; lint: string[] }

export interface FixResult {
  status: string
  model: string
  summary: string
  diff: string
  turns: number
  tokens: number
  citations: string[]
  before_shots: Record<string, string>
  verification: Verification | null
  attempts: { model: string; diff: string; lint_errors: string[]; verification: Verification | null }[]
  route: string
  states: string[]
}

export const CHECKS = ['lint', 'target_gone', 'no_new_findings', 'no_drift', 'build'] as const
export type Check = (typeof CHECKS)[number]

export interface Fix {
  id: string
  key: string
  model: string
  requested: string
  status: 'queued' | 'baseline' | 'working' | 'verifying' | 'verified' | 'failed' | 'budget' | 'gave_up' | 'error'
  baseline: { done: number; total: number }
  timeline: TimelineRow[]
  patches: Patch[]
  checks: Partial<Record<Check, boolean>>
  cells: Record<string, boolean>
  fallback: { from: string; to: string } | null
  result: FixResult | null
  error: string | null
}

export type Family = 'sam' | 'spark' | 'wonder' | 'grounding' | 'voice'

/** One event from the stream; every event has a type and the sequence number the server gave it. */
export interface Ev { type: string; seq: number; [k: string]: any } // eslint-disable-line @typescript-eslint/no-explicit-any

// ---------------------------------------------------------------------------------------------------- benchmark
export type BenchLabelValue = 'visible_defect' | 'no_visible_defect' | 'unsure'
export interface Rate { k: number; n: number; p: number; lo: number; hi: number }
export interface BenchRunRow { run: string; split: string | null; mode: string | null; n_cases: number; levels: string[]; usd: number | null; created: number; labelled: number; queue: number | null }
export interface BenchList { available: boolean; reason?: string | null; runs: BenchRunRow[] }
export interface QueueItem { id: string; n: number; route: string; width: number; height: number; theme: string; text_stress: string; target: string; tiles: string[]; label: BenchLabelValue | null }
export interface BenchQueue { run: string; split: string | null; question: string; items: QueueItem[]; done: number }
export interface HumanLevel {
  confusion: { tp: number; fp: number; fn: number; tn: number }
  precision: Rate | null; recall: Rate | null; clean_false_positive_rate: Rate | null
  precision_by_type: Record<string, Rate | null>; injected_recall_by_op: Record<string, Rate | null>
}
export interface BenchMetrics {
  run: string
  meta: { split?: string; seed?: number; mode?: string; targets?: string[]; code?: { commit: string | null; dirty: boolean | null }; usd?: number; seconds?: number }
  levels: string[]
  n_cases: number; n_mutated: number; n_clean: number
  construction: Record<string, Record<string, Rate | null>>
  injected_agreement: Record<string, Record<string, Rate | null>>
  localization: Record<string, Rate | null>
  labels: { n: number; visible_defect: number; no_visible_defect: number; unsure: number }
  human: Record<string, HumanLevel> | null
  headline: boolean
  caveats: string[]
  cost: { usd: number | null; model_calls: { live: number; cached: number } | null; seconds: number | null; usd_per_case: number | null; seconds_per_case: number | null }
}

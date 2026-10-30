import { create } from 'zustand'
import { api, type AppConfig, type Target } from './api'
import type {
  CandidateInfo, Check, Ev, Family, Finding, Fix, FixResult, RunInfo, StateDetail, StateInfo, Status, TimelineRow,
} from './types'
import { CHECKS } from './types'

/** Everything derived from the event stream. The UI is a pure function of this plus the user's selection, so replaying a
 *  recorded run's events rebuilds exactly the screen that was on show. */
export interface Data {
  lastSeq: number
  run: RunInfo | null
  states: Record<string, StateInfo>
  cands: Record<string, CandidateInfo[]>
  findings: Record<string, Finding>
  fixes: Record<string, Fix>
  fixOrder: string[]
  inflight: Record<Family, number>
  totalUsd: number
  calls: { kind: string; model?: string; source: string; usd: number }[]
  errors: string[]
  notes: string[]
  budgetHit: boolean
}

export const emptyData = (): Data => ({
  lastSeq: 0, run: null, states: {}, cands: {}, findings: {}, fixes: {}, fixOrder: [],
  inflight: { sam: 0, spark: 0, wonder: 0, grounding: 0, voice: 0 }, totalUsd: 0, calls: [], errors: [], notes: [], budgetHit: false,
})

export function familyOf(kind: string, model?: string | null): Family {
  if (kind.startsWith('sam')) return 'sam'
  if (kind === 'css.support') return 'grounding'
  if (kind === 'voice') return 'voice'
  if (kind === 'fix.turn') return (model ?? '').includes('wonder') ? 'wonder' : 'spark'
  return 'spark'
}

const newFix = (id: string, key: string, model: string): Fix => ({
  id, key, model, requested: model, status: 'baseline', baseline: { done: 0, total: 0 }, timeline: [], patches: [],
  checks: {}, cells: {}, fallback: null, result: null, error: null,
})

/** Pure: one event in, next data out. */
export function reduce(d: Data, ev: Ev): Data {
  if (ev.seq <= d.lastSeq) return d                                      // never apply an event twice
  const n: Data = { ...d, lastSeq: ev.seq }
  const fixOf = (): Fix | undefined => (ev.fix_id ? n.fixes[ev.fix_id] : undefined)
  const setFix = (patch: Partial<Fix>) => {
    const f = fixOf()
    if (f) n.fixes = { ...n.fixes, [f.id]: { ...f, ...patch } }
  }
  switch (ev.type) {
    case 'run.started': {
      const fresh = emptyData()
      return { ...fresh, lastSeq: ev.seq, run: { ...(ev as unknown as RunInfo), status: 'running' } }
    }
    case 'run.note': n.notes = [...d.notes, ev.note]; break
    case 'state.started':
      n.states = { ...d.states, [ev.state_key]: { key: ev.state_key, route: ev.route, width: ev.width, height: ev.height,
        theme: ev.theme, text_stress: ev.text_stress, status: 'running', tiles: [] } }
      break
    case 'state.captured':
      n.states = { ...d.states, [ev.state_key]: { ...(d.states[ev.state_key] ?? {} as StateInfo), key: ev.state_key,
        route: ev.route, width: ev.width, height: ev.height, theme: ev.theme, text_stress: ev.text_stress, status: 'captured',
        vw: ev.vw, vh: ev.vh, doc_w: ev.doc_w, doc_h: ev.doc_h, tiles: ev.tiles } }
      break
    case 'state.done':
      if (d.states[ev.state_key]) n.states = { ...d.states, [ev.state_key]: { ...d.states[ev.state_key], status: 'done' } }
      break
    case 'candidate.found': {
      const list = [...(d.cands[ev.state_key] ?? [])]
      list[ev.idx] = { state_key: ev.state_key, idx: ev.idx, defect: ev.defect, tile: ev.tile, metrics: ev.metrics, elements: ev.elements }
      n.cands = { ...d.cands, [ev.state_key]: list }
      break
    }
    case 'pixels.done': {
      const list = [...(d.cands[ev.state_key] ?? [])]
      if (list[ev.idx]) list[ev.idx] = { ...list[ev.idx], evidence: ev.evidence }
      n.cands = { ...d.cands, [ev.state_key]: list }
      break
    }
    case 'finding.updated': n.findings = { ...d.findings, [ev.finding.key]: ev.finding }; break
    case 'triage.done': {
      const f = d.findings[ev.key]
      if (f) n.findings = { ...d.findings, [ev.key]: { ...f, triage: ev.triage } }
      break
    }
    case 'model.start': {
      const fam = familyOf(ev.kind, ev.model)
      n.inflight = { ...d.inflight, [fam]: d.inflight[fam] + 1 }
      break
    }
    case 'model.call': {
      const fam = familyOf(ev.kind, ev.model)
      if (ev.source === 'live') n.inflight = { ...d.inflight, [fam]: Math.max(0, d.inflight[fam] - 1) }
      n.totalUsd = ev.total_usd ?? d.totalUsd
      n.calls = [...d.calls, { kind: ev.kind, model: ev.model, source: ev.source, usd: ev.usd ?? 0 }].slice(-300)
      break
    }
    case 'model.error': n.errors = [...d.errors, `${ev.kind}: ${ev.error}`]; break
    case 'budget.exceeded': n.budgetHit = true; break
    case 'run.done':
      if (d.run) n.run = { ...d.run, status: ev.status, counts: ev.counts }
      n.inflight = { sam: 0, spark: 0, wonder: 0, grounding: 0, voice: 0 }
      break
    case 'run.error':
      if (d.run) n.run = { ...d.run, status: 'failed' }
      n.errors = [...d.errors, ev.error]
      n.inflight = { sam: 0, spark: 0, wonder: 0, grounding: 0, voice: 0 }
      break

    // ---------------------------------------------------------------- a fix session
    case 'fix.started':
      n.fixes = { ...d.fixes, [ev.fix_id]: { ...newFix(ev.fix_id, ev.key, ev.model), baseline: { done: 0, total: ev.states } } }
      n.fixOrder = [...d.fixOrder, ev.fix_id]
      break
    case 'fix.queued': setFix({ status: 'queued' }); break
    case 'fix.baseline': setFix({ status: 'baseline', baseline: { done: ev.done ?? 0, total: ev.states } }); break
    case 'fix.tool': {
      const f = fixOf()
      if (f) {
        const row: TimelineRow = { id: f.timeline.length, name: ev.name, args: ev.args, status: 'running', detail: '' }
        setFix({ status: ev.name === 'finish' ? 'verifying' : 'working', timeline: [...f.timeline, row] })
      }
      break
    }
    case 'fix.tool.result': {
      const f = fixOf()
      if (f) {
        const i = [...f.timeline].reverse().findIndex(r => r.name === ev.name && r.status === 'running')
        if (i >= 0) {
          const idx = f.timeline.length - 1 - i
          const status = ev.blocked ? 'blocked' : ev.ok ? 'ok' : 'fail'
          const timeline = f.timeline.map((r, k) => (k === idx ? { ...r, status, detail: ev.detail } as TimelineRow : r))
          setFix({ timeline })
        }
      }
      break
    }
    case 'fix.patch': {
      const f = fixOf()
      if (f) setFix({ patches: [...f.patches, { diff: ev.diff, lint: ev.lint }] })
      break
    }
    case 'fix.verifying': setFix({ status: 'verifying', checks: {}, cells: {} }); break
    case 'fix.verify': {
      const f = fixOf()
      if (f && (CHECKS as readonly string[]).includes(ev.item)) setFix({ checks: { ...f.checks, [ev.item as Check]: ev.ok } })
      break
    }
    case 'fix.verify.state': {
      const f = fixOf()
      if (f) setFix({ cells: { ...f.cells, [ev.state_key]: ev.ok } })
      break
    }
    case 'fix.model_fallback': setFix({ fallback: { from: ev.from, to: ev.to }, model: ev.to }); break
    case 'fix.done': setFix({ status: ev.status === 'gave_up' ? 'gave_up' : ev.status, model: ev.model }); break
    case 'fix.result': {
      const r = ev as unknown as FixResult & { fix_id: string }
      setFix({ result: r, status: r.status as Fix['status'], model: r.model, cells: r.verification?.grid ?? fixOf()?.cells ?? {} })
      break
    }
    case 'fix.error': setFix({ status: 'error', error: ev.error }); break
    default: break
  }
  return n
}

// ------------------------------------------------------------------------------------------------ the store
export interface Layers { dom: boolean; sam: boolean; candidates: boolean; findings: boolean }
export type ChipHover = 'geometry' | 'pixels' | 'spark' | null

interface Ui {
  view: 'scan' | 'bench'
  runId: string | null
  stateKey: string | null
  tile: number
  route: string | null
  theme: string
  stress: string
  findingKey: string | null
  hoverKey: string | null
  hoverChip: ChipHover
  layers: Layers
  tab: Status
  drawer: boolean
  fixId: string | null
  details: Record<string, StateDetail>
  labels: Record<string, string>
  targets: Target[]
  appConfig: AppConfig | null
  pickConfig: string
  pickRoute: string
  useModels: boolean
}

interface Store extends Data, Ui {
  applyEvent: (ev: Ev) => void
  reset: (runId: string | null) => void
  set: (p: Partial<Ui>) => void
  selectState: (key: string, tile?: number) => void
  selectFinding: (key: string | null) => void
  toggleLayer: (l: keyof Layers) => void
  loadDetail: (key: string) => Promise<void>
}

const baseUi = (): Ui => ({
  view: 'scan', runId: null, stateKey: null, tile: 0, route: null, theme: 'light', stress: 'none', findingKey: null,
  hoverKey: null, hoverChip: null, layers: { dom: false, sam: true, candidates: false, findings: true }, tab: 'confirmed',
  drawer: false, fixId: null, details: {}, labels: {}, targets: [], appConfig: null, pickConfig: '', pickRoute: '', useModels: true,
})

export const stateKeyFor = (states: Record<string, StateInfo>, route: string | null, width: number, theme: string, stress: string) =>
  Object.values(states).find(s => s.route === route && s.width === width && s.theme === theme && s.text_stress === stress)?.key ?? null

export const useStore = create<Store>((set, get) => ({
  ...emptyData(),
  ...baseUi(),

  applyEvent: ev => {
    const s = get()
    const next = reduce(s, ev)
    if (next === s) return
    const patch: Partial<Store> = { ...next }
    // keep the selection sensible as data arrives
    if (ev.type === 'state.captured' && !s.stateKey) {
      patch.stateKey = ev.state_key; patch.tile = 0; patch.route = ev.route; patch.theme = ev.theme; patch.stress = ev.text_stress
    }
    if (ev.type === 'run.started') Object.assign(patch, { ...baseUi(), view: s.view, runId: s.runId, labels: s.labels, targets: s.targets, appConfig: s.appConfig, pickConfig: s.pickConfig, pickRoute: s.pickRoute, useModels: s.useModels })
    if (ev.type === 'fix.started') { patch.drawer = true; patch.fixId = ev.fix_id }
    set(patch)
    if (ev.type === 'state.done' && get().stateKey === ev.state_key) void get().loadDetail(ev.state_key)
    if (ev.type === 'finding.updated' && !get().findingKey) {
      const top = Object.values(get().findings).find(f => f.status === 'confirmed')
      if (top) get().selectFinding(top.key)
    }
  },

  reset: runId => set(s => ({ ...emptyData(), ...baseUi(), runId, labels: {}, targets: s.targets, appConfig: s.appConfig, pickConfig: s.pickConfig, pickRoute: s.pickRoute, useModels: s.useModels })),
  set: p => set(p),

  selectState: (key, tile = 0) => {
    const st = get().states[key]
    if (!st) return
    set({ stateKey: key, tile, route: st.route, theme: st.theme, stress: st.text_stress })
    void get().loadDetail(key)
  },

  selectFinding: key => {
    if (!key) { set({ findingKey: null }); return }
    const { findings, states, theme, stress } = get()
    const f = findings[key]
    if (!f) return
    // jump to the narrowest-width state where it reproduces, in the current theme and text-stress if possible
    const cands = [...f.candidates].sort((a, b) => (states[a.state_key]?.width ?? 1e9) - (states[b.state_key]?.width ?? 1e9))
    const pref = cands.find(c => states[c.state_key]?.theme === theme && states[c.state_key]?.text_stress === stress) ?? cands[0]
    set({ findingKey: key, tab: f.status })
    if (pref && states[pref.state_key]) get().selectState(pref.state_key, pref.tile)
  },

  toggleLayer: l => set(s => ({ layers: { ...s.layers, [l]: !s.layers[l] } })),

  loadDetail: async key => {
    const { runId, details, states, run } = get()
    if (!runId || details[key]) return
    // a live state is saved just after it is captured; wait for state.done (logs recorded before that event existed are complete)
    if (run?.status === 'running' && states[key]?.status !== 'done') return
    try {
      const d = await api.state(runId, key)
      set(s => ({ details: { ...s.details, [key]: d } }))
    } catch { /* the next selection retries */ }
  },
}))

// ------------------------------------------------------------------------------------------------ selectors
export const SEVERITY_BY_TYPE: Record<string, number> = {
  viewport_protrusion: 3, occlusion: 3, clipped_text: 3, element_protrusion: 2, collision: 2, small_target: 2, contrast: 2,
}

export const severityOf = (f: Finding) => f.triage?.severity ?? SEVERITY_BY_TYPE[f.type] ?? 2

export function sortedFindings(findings: Record<string, Finding>, status: Status): Finding[] {
  return Object.values(findings).filter(f => f.status === status)
    .sort((a, b) => severityOf(b) - severityOf(a) || a.type.localeCompare(b.type) || a.key.localeCompare(b.key))
}

export function counts(findings: Record<string, Finding>): Record<Status, number> {
  const c: Record<Status, number> = { confirmed: 0, needs_review: 0, dismissed: 0, not_observable: 0 }
  for (const f of Object.values(findings)) c[f.status]++
  return c
}

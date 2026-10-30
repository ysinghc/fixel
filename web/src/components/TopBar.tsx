import { useEffect, useState } from 'react'
import { api, type AppConfig, type RunRow, type Target } from '../api'
import { money } from '../fmt'
import { useStore } from '../store'
import type { Family } from '../types'
import { Button, Chip, Dot } from './ui'

const PILLS: { fam: Family; label: string; model: string; color: string; unbuilt?: boolean }[] = [
  { fam: 'sam', label: 'SAM', model: 'sam-3.1', color: '#14b8a6' },
  { fam: 'spark', label: 'Spark', model: 'muse-spark-1.3', color: '#38bdf8' },
  { fam: 'wonder', label: 'Wonder', model: 'muse-wonder-1.0', color: '#a78bfa' },
  { fam: 'grounding', label: 'Grounding', model: 'web_search', color: '#fbbf24' },
  { fam: 'voice', label: 'Voice', model: 'not built yet', color: '#52525b', unbuilt: true },
]

export function ModelPills() {
  const inflight = useStore(s => s.inflight)
  const calls = useStore(s => s.calls)
  return (
    <div className="flex items-center gap-1.5">
      {PILLS.map(p => {
        const n = inflight[p.fam]
        const used = calls.filter(c => (p.fam === 'sam' ? c.kind.startsWith('sam') : p.fam === 'grounding' ? c.kind === 'css.support'
          : p.fam === 'wonder' ? (c.model ?? '').includes('wonder') : p.fam === 'spark' ? c.kind === 'spark.triage' : false))
        const live = used.filter(c => c.source === 'live').length
        return (
          <span key={p.fam} title={p.unbuilt ? 'Voice intake is not built yet' : `${p.model}: ${used.length} calls (${live} live, ${used.length - live} cached)`}
            data-testid={`pill-${p.fam}`} data-active={n > 0}
            className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] ${n > 0 ? 'border-white/30 bg-white/5 text-white' : 'border-line text-muted'} ${p.unbuilt ? 'opacity-50' : ''}`}>
            <Dot color={p.color} pulse={n > 0} size={7} />
            {p.label}
            {used.length > 0 && <span className="tabular-nums text-[10px] text-zinc-500">{used.length}</span>}
          </span>
        )
      })}
    </div>
  )
}

export function CostMeter() {
  const total = useStore(s => s.totalUsd)
  const budget = useStore(s => s.run?.budget_usd) ?? 10
  const hit = useStore(s => s.budgetHit)
  return (
    <span title="Spend on live model calls this run. Cached answers cost nothing." data-testid="cost"
      className={`tabular-nums text-xs ${hit ? 'text-red-300' : 'text-zinc-300'}`}>
      {money(total)} <span className="text-muted">/ ${budget}</span>
    </span>
  )
}

export function ModeBadge({ mode }: { mode: AppConfig['mode'] | undefined }) {
  if (!mode) return null
  const replay = mode === 'replay'
  return (
    <span data-testid="mode" title={replay ? 'Model answers come from the cache; nothing is spent'
      : mode === 'record' ? 'Live model calls, cached for replay' : 'Always calling the models'}
      className={`rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${replay ? 'bg-amber-400 text-black' : 'bg-emerald-500/20 text-emerald-300'}`}>
      {replay ? 'REPLAY' : 'LIVE'}
    </span>
  )
}

export function TopBar({ config, targets }: { config: AppConfig | null; targets: Target[] }) {
  const run = useStore(s => s.run)
  const view = useStore(s => s.view)
  const runId = useStore(s => s.runId)
  const config_ = useStore(s => s.pickConfig)
  const route = useStore(s => s.pickRoute)
  const useModels = useStore(s => s.useModels)
  const setConfigPath = (v: string) => useStore.getState().set({ pickConfig: v })
  const setRoute = (v: string) => useStore.getState().set({ pickRoute: v })
  const setUseModels = (v: boolean) => useStore.getState().set({ useModels: v })
  const [pastRuns, setPastRuns] = useState<RunRow[]>([])
  const [error, setError] = useState('')
  const running = run?.status === 'running'

  useEffect(() => {
    if (targets.length && !config_) {
      const t = targets.find(x => x.name === 'demo-shop') ?? targets.find(x => x.split === 'demo') ?? targets[0]     // the planted-defect demo first
      useStore.getState().set({ pickConfig: t.config, pickRoute: t.routes[0] })
    }
  }, [targets, config_])
  useEffect(() => { api.runs().then(setPastRuns).catch(() => {}) }, [run?.status, runId])
  useEffect(() => { if (config) setUseModels(config.models_available) }, [config])  // eslint-disable-line react-hooks/exhaustive-deps

  const target = targets.find(t => t.config === config_)
  const states = target ? (route === '*' ? target.routes.length : 1) * target.widths.length * target.themes.length * target.text_stress.length : 0

  const scan = async () => {
    setError('')
    try {
      const { run_id } = await api.scan({ config: config_, routes: route === '*' ? undefined : [route], models: useModels })
      useStore.getState().reset(run_id)
    } catch (e) { setError((e as Error).message) }
  }

  return (
    <header className="flex h-12 flex-none items-center gap-3 border-b border-line bg-panel px-3">
      <div className="flex items-center gap-2 pr-1">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-sky-500 text-xs font-black text-white">F</span>
        <span className="text-sm font-semibold tracking-tight">Fixel</span>
      </div>

      <nav className="flex items-center gap-1">
        {(['scan', 'bench'] as const).map(v => (
          <button key={v} onClick={() => useStore.getState().set({ view: v })} data-testid={`tab-${v}`}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${view === v ? 'bg-white/10 text-white' : 'text-muted hover:text-zinc-200'}`}>
            {v === 'scan' ? 'Scan' : 'Benchmark'}
          </button>
        ))}
      </nav>

      <div className="mx-1 h-5 w-px bg-line" />

      <select value={config_} onChange={e => { setConfigPath(e.target.value); setRoute(targets.find(t => t.config === e.target.value)?.routes[0] ?? '') }}
        data-testid="target-select" className="h-7 rounded-md border border-line bg-raised px-2 text-xs">
        {targets.map(t => <option key={t.config} value={t.config}>{t.name}{t.split ? ` · ${t.split}` : ''}</option>)}
      </select>
      <select value={route} onChange={e => setRoute(e.target.value)} data-testid="route-select"
        className="h-7 max-w-40 rounded-md border border-line bg-raised px-2 text-xs">
        {target?.routes.map(r => <option key={r} value={r}>{r}</option>)}
        {target && target.routes.length > 1 && <option value="*">all routes</option>}
      </select>
      <label className="flex items-center gap-1.5 text-xs text-zinc-400" title={config?.models_available ? 'SAM and Spark add pixel evidence and a verdict' : 'No API key: geometry and the opacity diff only'}>
        <input type="checkbox" checked={useModels} disabled={!config?.models_available} onChange={e => setUseModels(e.target.checked)} data-testid="models-toggle" />
        models
      </label>
      {running
        ? <Button kind="danger" onClick={() => runId && api.cancel(runId).catch(() => {})} data-testid="cancel">Cancel</Button>
        : <Button kind="primary" onClick={scan} disabled={!config_} title={`Renders ${states} states`} data-testid="scan-button">Scan <span className="opacity-70">{states} states</span></Button>}
      <Button disabled title="Voice intake is not built yet">🎙</Button>
      {error && <span className="max-w-64 truncate text-xs text-red-300" title={error} data-testid="scan-error">{error}</span>}

      <select value="" onChange={e => { if (e.target.value) useStore.getState().reset(e.target.value) }} data-testid="past-runs"
        className="h-7 w-28 rounded-md border border-line bg-raised px-2 text-xs text-zinc-400" title="Replay a recorded run from its event log">
        <option value="">Open run…</option>
        {pastRuns.filter(r => r.kind === 'scan').map(r => (
          <option key={r.id} value={r.id}>{new Date(r.created * 1000).toLocaleTimeString()} · {r.config.config.replace('targets/', '').replace('.yaml', '')} · {r.status}</option>
        ))}
      </select>

      <div className="ml-auto flex items-center gap-3">
        {run?.split === 'test' && <Chip tone="amber" title="Test split: report its numbers, never tune on it">test split</Chip>}
        <ModelPills />
        <CostMeter />
        <ModeBadge mode={config?.mode} />
      </div>
    </header>
  )
}

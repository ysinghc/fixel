import { NavLink } from 'react-router-dom'
import { api } from '../api'
import { money } from '../fmt'
import { paths } from '../paths'
import { useStore } from '../store'
import type { Family } from '../types'
import { RunStatusChip, SplitChip } from './RunBits'
import { Button, Dot, Progress } from './ui'

const PILLS: { fam: Family; label: string; color: string }[] = [
  { fam: 'sam', label: 'SAM', color: '#14b8a6' }, { fam: 'spark', label: 'Spark', color: '#38bdf8' }, { fam: 'wonder', label: 'Wonder', color: '#a78bfa' },
]

/** Which models are working right now: shown only on a run, where it means something (Occam's razor). */
function ModelActivity() {
  const inflight = useStore(s => s.inflight)
  const calls = useStore(s => s.calls)
  const total = useStore(s => s.totalUsd)
  const budget = useStore(s => s.run?.budget_usd) ?? 10
  const hit = useStore(s => s.budgetHit)
  return (
    <div className="flex items-center gap-3 text-[11px] text-muted" data-testid="model-activity">
      {PILLS.map(p => {
        const n = calls.filter(c => (p.fam === 'sam' ? c.kind.startsWith('sam') : p.fam === 'wonder' ? (c.model ?? '').includes('wonder') : c.kind === 'spark.triage')).length
        return (
          <span key={p.fam} className={`flex items-center gap-1.5 ${inflight[p.fam] > 0 ? 'text-zinc-100' : ''}`} data-testid={`pill-${p.fam}`} data-active={inflight[p.fam] > 0}
            title={`${p.label}: ${n} calls`}>
            <Dot color={p.color} pulse={inflight[p.fam] > 0} size={7} />{p.label}{n > 0 && <span className="tabular-nums">{n}</span>}
          </span>
        )
      })}
      <span className={`tabular-nums ${hit ? 'text-red-300' : ''}`} data-testid="cost" title="Spend on live model calls in this run. Cached answers cost nothing.">{money(total)} of ${budget}</span>
    </div>
  )
}

/** The run's name, state and two sub-pages. Progress is visible from anywhere in the run (Doherty threshold, goal gradient). */
export function RunHeader() {
  const run = useStore(s => s.run)
  const runId = useStore(s => s.runId)
  const states = useStore(s => s.states)
  const errors = useStore(s => s.errors)
  const notes = useStore(s => s.notes)
  if (!run || !runId) return <div className="skeleton mb-6 h-20 rounded-xl" data-testid="run-loading" />
  const done = Object.values(states).filter(s => s.status === 'done').length
  const running = run.status === 'running'
  return (
    <div className="mb-6" data-testid="run-header">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{run.target}</h1>
        <RunStatusChip status={run.status} />
        <SplitChip split={run.split} />
        <span className="text-xs text-muted">{run.routes.length === 1 ? 'Page' : 'Pages'} <code className="font-mono">{run.routes.join(', ')}</code> · {run.states} screens · {run.models ? 'full check' : 'quick check (no models)'}</span>
        <div className="ml-auto flex items-center gap-4">
          {run.models && <ModelActivity />}
          {running && <Button kind="danger" onClick={() => api.cancel(runId).catch(() => {})} data-testid="cancel">Stop scan</Button>}
        </div>
      </div>
      {running && (
        <div className="mt-3 max-w-xl" data-testid="run-progress">
          <div className="mb-1 flex text-xs text-muted"><span>Rendering and checking screens</span><span className="ml-auto tabular-nums">{done} of {run.states}</span></div>
          <Progress value={done} total={run.states} />
        </div>
      )}
      {run.status === 'failed' && <div className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200" data-testid="run-error">The scan failed: {errors[errors.length - 1]}</div>}
      {notes.map(n => <div key={n} className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">{n}</div>)}
      <nav className="mt-5 flex gap-1 border-b border-line">
        {[{ to: paths.run(runId), label: 'Findings', end: true, testid: 'subnav-findings' }, { to: paths.screens(runId), label: 'Screens', end: false, testid: 'subnav-screens' }].map(t => (
          <NavLink key={t.to} to={t.to} end={t.end} data-testid={t.testid}
            className={({ isActive }) => `-mb-px border-b-2 px-3 py-2 text-[13px] font-medium ${isActive ? 'border-sky-400 text-white' : 'border-transparent text-muted hover:text-zinc-200'}`}>{t.label}</NavLink>
        ))}
      </nav>
    </div>
  )
}

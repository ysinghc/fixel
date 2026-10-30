import { useState } from 'react'
import { api } from '../api'
import { SEVERITY_COLOR, TYPE_LABEL, geometryText, locLabel, pixelsText, representative, widthRange } from '../fmt'
import { counts, severityOf, sortedFindings, useStore } from '../store'
import { STATUSES, type Finding, type Status } from '../types'
import { Button, Chip, Dot } from './ui'

const TAB_LABEL: Record<Status, string> = { confirmed: 'Confirmed', needs_review: 'Needs review', dismissed: 'Dismissed', not_observable: 'Not observable' }
const TAB_HELP: Record<Status, string> = {
  confirmed: 'Geometry and pixels agree, and no model argued it away.',
  needs_review: 'The model disagrees with the pixels: a person should look.',
  dismissed: 'Rejected, and shown so you can check: scrolls apart by design, or judged intentional.',
  not_observable: 'The boxes collide but nothing visible changes. Dropped from the defect list.',
}

function SparkChip({ f, hasModels, running }: { f: Finding; hasModels: boolean; running: boolean }) {
  const set = useStore(s => s.set)
  const t = f.triage
  const hover = { onEnter: () => set({ hoverChip: 'spark' }), onLeave: () => set({ hoverChip: null }) }
  if (t) {
    const tone = t.verdict === 'real_defect' ? 'red' : t.verdict === 'intentional' ? 'zinc' : 'amber'
    return <Chip tone={tone} {...hover} title={t.fix_hint}>Spark: {t.verdict.replace('_', ' ')} {Math.round(t.confidence * 100)}%</Chip>
  }
  if (f.status === 'dismissed') return <Chip tone="zinc" {...hover} title="Decided by code: the elements can be scrolled apart">dismissed by code</Chip>
  if (!hasModels) return <Chip tone="zinc" {...hover}>Spark unavailable — geometry and pixels only</Chip>
  return <Chip tone="zinc" {...hover}>{running ? 'Spark: pending…' : 'Spark: not asked'}</Chip>
}

function FindingCard({ f }: { f: Finding }) {
  const states = useStore(s => s.states)
  const run = useStore(s => s.run)
  const runId = useStore(s => s.runId)
  const sel = useStore(s => s.findingKey)
  const label = useStore(s => s.labels[f.key])
  const fixes = useStore(s => s.fixes)
  const set = useStore(s => s.set)
  const selectFinding = useStore(s => s.selectFinding)
  const [err, setErr] = useState('')

  const { index } = representative(f, states)
  const ev = f.evidence[index]
  const sev = severityOf(f)
  const fix = Object.values(fixes).filter(x => x.key === f.key).at(-1)
  const busy = fix && ['queued', 'baseline', 'working', 'verifying'].includes(fix.status)

  const startFix = async () => {
    if (!runId) return
    setErr('')
    try { await api.fix(runId, f.key) } catch (e) { setErr((e as Error).message) }
  }
  const markWrong = async () => {
    if (!runId) return
    try { await api.label(runId, f.key, 'no_visible_defect'); set({ labels: { ...useStore.getState().labels, [f.key]: 'no_visible_defect' } }) }
    catch (e) { setErr((e as Error).message) }
  }

  return (
    <article data-testid="finding-card" data-key={f.key} data-selected={sel === f.key}
      onClick={() => selectFinding(f.key)} onMouseEnter={() => set({ hoverKey: f.key })} onMouseLeave={() => set({ hoverKey: null })}
      className={`cursor-pointer rounded-lg border p-3 transition-colors ${sel === f.key ? 'border-sky-500/60 bg-sky-500/[0.07]' : 'border-line bg-raised hover:border-zinc-600'}`}>
      <div className="flex items-center gap-2">
        <Dot color={SEVERITY_COLOR[sev] ?? '#64748b'} />
        <span className="text-[13px] font-semibold">{TYPE_LABEL[f.type] ?? f.type}</span>
        <Chip tone="zinc" className="ml-auto tabular-nums" title="Widths in the scanned matrix where it reproduces">{widthRange(f.widths)}</Chip>
      </div>

      <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-zinc-300" data-testid="sentence">
        {f.triage?.what_the_user_sees ?? (run?.models ? 'Waiting for Spark to describe what a user sees…' : 'No description: models are off for this run.')}
      </p>

      <div className="mt-2 flex flex-wrap gap-1.5" data-testid="chips">
        <Chip tone="amber" title="The geometry oracle and its measurement"
          onEnter={() => set({ hoverChip: 'geometry' })} onLeave={() => set({ hoverChip: null })}>Geometry: {geometryText(f)}</Chip>
        <Chip tone="teal" title="Opacity diff (hide one element, count changed pixels) and SAM's confidence that a distinct object is painted there"
          onEnter={() => set({ hoverChip: 'pixels' })} onLeave={() => set({ hoverChip: null })}>Pixels: {pixelsText(f, ev)}</Chip>
        <SparkChip f={f} hasModels={!!run?.models} running={run?.status === 'running'} />
      </div>

      <div className="mt-2.5 flex items-center gap-2">
        {f.locs[0]
          ? <code className="truncate rounded bg-black/30 px-1.5 py-0.5 font-mono text-[11px] text-sky-300" title={f.locs.join('\n')}>{locLabel(f.locs[0])}</code>
          : <span className="text-[11px] text-muted" title="No source location (not a React/Vite/Next target)">no source link</span>}
        <div className="ml-auto flex gap-1.5" onClick={e => e.stopPropagation()}>
          {f.status === 'confirmed' && (
            <Button kind="primary" onClick={startFix} disabled={!!busy || !!run?.status && run.status === 'running'} data-testid="fix-button"
              title={fix?.status === 'verified' ? 'A verified fix already exists: run again' : 'Repair this in an isolated worktree and verify it across the whole matrix'}>
              {busy ? 'Fixing…' : fix?.status === 'verified' ? 'Fixed ✓' : fix ? 'Retry fix' : 'Fix'}
            </Button>
          )}
          <Button onClick={markWrong} disabled={!!label} data-testid="mark-wrong" title="Record that a person sees no defect here. Feeds the benchmark's human labels.">
            {label ? 'Marked' : 'Mark wrong'}
          </Button>
        </div>
      </div>
      {err && <div className="mt-2 text-[11px] text-red-300" data-testid="card-error">{err}</div>}
    </article>
  )
}

export function FindingsPanel() {
  const findings = useStore(s => s.findings)
  const tab = useStore(s => s.tab)
  const run = useStore(s => s.run)
  const set = useStore(s => s.set)
  const c = counts(findings)
  const list = sortedFindings(findings, tab)

  return (
    <aside className="flex w-[380px] flex-none flex-col border-l border-line bg-panel" data-testid="findings">
      <div className="flex border-b border-line">
        {STATUSES.map(s => (
          <button key={s} onClick={() => set({ tab: s })} data-testid={`tab-${s}`} data-active={tab === s}
            title={TAB_HELP[s]}
            className={`flex-1 whitespace-nowrap border-b-2 px-1 py-2.5 text-[11px] font-medium transition-colors ${tab === s ? 'border-sky-400 text-white' : 'border-transparent text-muted hover:text-zinc-200'}`}>
            {TAB_LABEL[s]} <span className={`tabular-nums ${tab === s ? 'text-sky-300' : 'text-zinc-600'}`} data-testid={`count-${s}`}>{c[s]}</span>
          </button>
        ))}
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {!run && <p className="p-2 text-xs text-muted">Findings appear here, with the evidence behind each one.</p>}
        {run && list.length === 0 && (
          <p className="rounded-lg border border-dashed border-line p-4 text-xs text-muted">
            {run.status === 'running' ? 'Looking…' : tab === 'confirmed' ? 'Nothing confirmed.' : `Nothing here. ${TAB_HELP[tab]}`}
          </p>
        )}
        {list.map(f => <FindingCard key={f.key} f={f} />)}
      </div>
    </aside>
  )
}

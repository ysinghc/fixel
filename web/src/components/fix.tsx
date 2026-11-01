import { useMemo, useState } from 'react'
import { api } from '../api'
import { CHECKS, type Check, type Fix, type TimelineRow } from '../types'
import { Chip, Dot } from './ui'

export const CHECK_LABEL: Record<Check, string> = {
  lint: 'Linter accepts the patch', target_gone: 'Target defect gone in every state', no_new_findings: 'No new defects',
  no_drift: 'Nothing else moved or resized', build: 'Build passes',
}
export const TOOL_ICON: Record<string, string> = { read_file: '📄', search: '🔎', edit_file: '✎', reset: '↺', rerender: '⟳', check_css_support: '🌐', finish: '⚑' }

function describe(r: TimelineRow): string {
  const a = r.args as Record<string, string | number>
  switch (r.name) {
    case 'read_file': return `read_file ${a.path ?? ''}`
    case 'search': return `search /${a.pattern ?? ''}/`
    case 'edit_file': return `edit_file ${a.path ?? ''}`
    case 'check_css_support': return `check_css_support ${a.feature ?? ''}`
    case 'finish': return 'finish'
    default: return r.name
  }
}

export function Timeline({ fix }: { fix: Fix }) {
  return (
    <div data-testid="timeline">
      <ol className="space-y-1.5">
        {fix.status === 'queued' && <li className="text-xs text-muted">Waiting for the running fix session to finish…</li>}
        {fix.status === 'baseline' && (
          <li className="text-xs text-zinc-300" data-testid="baseline">
            Baseline scan of the unpatched code <span className="tabular-nums text-muted">{fix.baseline.done}/{fix.baseline.total}</span>
            <div className="mt-1 h-1 overflow-hidden rounded bg-line"><div className="h-full bg-sky-500 transition-all" style={{ width: `${fix.baseline.total ? (fix.baseline.done / fix.baseline.total) * 100 : 0}%` }} /></div>
          </li>
        )}
        {fix.timeline.length === 0 && !["queued", "baseline"].includes(fix.status) && <li className="text-xs text-muted">Waiting for the model's first step…</li>}
        {fix.timeline.map(r => (
          <li key={r.id} data-testid="timeline-row" data-status={r.status} data-name={r.name}
            className={`rounded-lg border px-3 py-2 text-xs ${r.status === 'blocked' ? 'border-red-500/50 bg-red-500/10' : r.status === 'fail' ? 'border-amber-500/40 bg-amber-500/5' : 'border-line bg-raised'}`}>
            <div className="flex items-center gap-1.5">
              <span className="w-4 text-center">{TOOL_ICON[r.name] ?? '•'}</span>
              <span className="min-w-0 flex-1 truncate font-mono text-[11px]">{describe(r)}</span>
              {r.status === 'running' && <Dot color="#38bdf8" pulse size={6} />}
              {r.status === 'ok' && <span className="text-emerald-400">✓</span>}
              {r.status === 'blocked' && <span className="text-[10px] font-bold uppercase text-red-300">blocked</span>}
              {r.status === 'fail' && <span className="text-amber-400">!</span>}
            </div>
            {r.detail && <div className={`mt-0.5 pl-5 text-[11px] ${r.status === 'blocked' ? 'text-red-300' : 'text-muted'}`}>{r.detail}</div>}
          </li>
        ))}
        {fix.status === 'error' && <li className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-200" data-testid="fix-error">{fix.error}</li>}
      </ol>
    </div>
  )
}

function DiffLine({ line }: { line: string }) {
  const kind = line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') || line.startsWith('index ') ? 'head'
    : line.startsWith('@@') ? 'hunk' : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : 'ctx'
  const bg = { head: 'text-zinc-500', hunk: 'bg-sky-500/10 text-sky-300', add: 'bg-emerald-500/15 text-emerald-100', del: 'bg-red-500/15 text-red-100', ctx: 'text-zinc-400' }[kind]
  // tint quoted strings (class names, copy) and tag names so a one-token change is easy to spot
  const parts = kind === 'head' || kind === 'hunk' ? [line] : line.split(/("[^"]*"|'[^']*')/g)
  return (
    <div className={`whitespace-pre px-2 ${bg}`} data-kind={kind}>
      {parts.map((p, i) => (i % 2 === 1 ? <span key={i} className={kind === 'ctx' ? 'text-amber-200/70' : 'text-amber-200'}>{p}</span> : <span key={i}>{p || ' '}</span>))}
    </div>
  )
}

export function Diffs({ fix }: { fix: Fix }) {
  const tabs = useMemo(() => {
    const t = fix.patches.map((p, i) => ({ id: `e${i}`, label: `Edit ${i + 1}`, blocked: p.lint.length > 0, diff: p.diff, lint: p.lint }))
    if (fix.result?.diff) t.push({ id: 'final', label: fix.result.status === 'verified' ? 'Final patch ✓' : 'Final patch', blocked: false, diff: fix.result.diff, lint: [] })
    return t
  }, [fix.patches, fix.result])
  const [pick, setPick] = useState<string | null>(null)
  const active = tabs.find(t => t.id === pick) ?? tabs[tabs.length - 1]
  return (
    <div data-testid="diffs">
      <div className="mb-2 flex flex-none flex-wrap items-center gap-1">
        <span className="mr-2 text-xs text-muted">Show</span>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setPick(t.id)} data-testid="diff-tab" data-blocked={t.blocked}
            className={`rounded-md border px-2 py-0.5 text-[11px] ${active?.id === t.id ? 'border-white/30 bg-white/10 text-white' : 'border-line text-muted hover:text-zinc-200'} ${t.blocked ? '!border-red-500/50 text-red-300' : ''}`}>
            {t.label}{t.blocked ? ' ✗' : ''}
          </button>
        ))}
      </div>
      {!active
        ? <p className="text-xs text-muted">No edits yet. Each edit the model makes appears here, linted before it is kept.</p>
        : (
          <div className="max-h-[60vh] overflow-auto rounded-lg border border-line bg-black/30 font-mono text-[12px] leading-5" data-testid="diff">
            {active.blocked && (
              <div className="border-b border-red-500/40 bg-red-500/10 px-2 py-1.5 font-sans text-xs text-red-200" data-testid="lint-reasons">
                Blocked by the linter, and reverted: {active.lint.join('; ')}
              </div>
            )}
            {active.diff.split('\n').map((l, i) => <DiffLine key={i} line={l} />)}
          </div>
        )}
    </div>
  )
}

export function BeforeAfter({ fix, before, after }: { fix: Fix; before?: string; after?: string }) {
  const [x, setX] = useState(50)
  if (!before || !after) {
    return (
      <div className="grid h-60 place-items-center rounded-lg border border-dashed border-line text-xs text-muted" data-testid="before-after-empty">
        {fix.status === 'verifying' ? 'Re-rendering the patched page…' : 'Before / after appears once the patch is verified'}
      </div>
    )
  }
  return (
    <div data-testid="before-after">
      <div className="relative mx-auto aspect-[3/4] max-h-[460px] overflow-hidden rounded-lg border border-line bg-white" style={{ ['--x' as string]: `${x}%` }}>
        <img src={api.artifact(after)} alt="after the patch" className="absolute inset-0 h-full w-full object-cover object-top" />
        <img src={api.artifact(before)} alt="before the patch" className="ba-top absolute inset-0 h-full w-full object-cover object-top" />
        <div className="absolute inset-y-0 w-0.5 bg-sky-400 shadow" style={{ left: `${x}%` }} />
        <span className="absolute left-1 top-1 rounded bg-black/70 px-1 text-[10px] text-white">before</span>
        <span className="absolute right-1 top-1 rounded bg-black/70 px-1 text-[10px] text-white">after</span>
      </div>
      <input type="range" min={0} max={100} value={x} onChange={e => setX(Number(e.target.value))} className="mt-1.5 w-full accent-sky-400" aria-label="before/after" data-testid="slider" />
    </div>
  )
}

export function Grid({ fix, states }: { fix: Fix; states: string[] }) {
  const parsed = states.map(k => { const [, w, theme, stress] = k.split('|'); return { key: k, w: Number(w), row: `${theme} · ${stress === 'pseudo' ? 'pseudo-loc' : 'normal'}` } })
  const widths = [...new Set(parsed.map(p => p.w))].sort((a, b) => a - b)
  const rows = [...new Set(parsed.map(p => p.row))]
  const cell = (row: string, w: number) => parsed.find(p => p.row === row && p.w === w)
  return (
    <div data-testid="grid" className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0.5 text-[11px]">
        <thead><tr><th />{widths.map(w => <th key={w} className="font-normal tabular-nums text-muted">{w}</th>)}</tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r}>
              <td className="whitespace-nowrap pr-1 text-right text-muted">{r}</td>
              {widths.map(w => {
                const c = cell(r, w)
                const v = c ? fix.cells[c.key] : undefined
                return (
                  <td key={w} data-testid="grid-cell" data-state={v === undefined ? 'pending' : v ? 'ok' : 'fail'} title={c?.key}
                    className={`h-7 min-w-9 rounded text-center ${v === undefined ? 'bg-[#1d222d]' : v ? 'bg-emerald-500/70' : 'bg-red-500/80'}`}>
                    {v === undefined ? '' : v ? '✓' : '✗'}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CheckList({ fix }: { fix: Fix }) {
  return (
    <ul className="space-y-1.5" data-testid="checklist">
      {CHECKS.map(c => {
        const v = fix.checks[c]
        return (
          <li key={c} data-testid="check" data-check={c} data-state={v === undefined ? 'pending' : v ? 'ok' : 'fail'} className="flex items-center gap-2 text-[13px]">
            <span className={`grid h-5 w-5 flex-none place-items-center rounded-full text-[11px] ${v === undefined ? 'border border-line text-transparent' : v ? 'bg-emerald-500/80 text-black' : 'bg-red-500 text-white'}`}>{v ? '✓' : v === false ? '✗' : '·'}</span>
            <span className={v === false ? 'font-medium text-red-300' : v ? 'text-zinc-200' : 'text-muted'}>{CHECK_LABEL[c]}</span>
          </li>
        )
      })}
    </ul>
  )
}

export const FIX_STATUS: Record<Fix['status'], { tone: 'zinc' | 'blue' | 'green' | 'red' | 'amber'; text: string }> = {
  queued: { tone: 'zinc', text: 'queued' }, baseline: { tone: 'blue', text: 'baseline scan' }, working: { tone: 'blue', text: 'working' },
  verifying: { tone: 'blue', text: 'verifying' }, verified: { tone: 'green', text: 'verified' }, failed: { tone: 'red', text: 'not verified' },
  budget: { tone: 'amber', text: 'budget reached' }, gave_up: { tone: 'amber', text: 'gave up' }, error: { tone: 'red', text: 'error' },
}
export const isBusy = (f?: Fix) => !!f && ['queued', 'baseline', 'working', 'verifying'].includes(f.status)
export const modelName = (m: string) => (m.includes('wonder') ? 'Wonder' : m.includes('spark') ? 'Spark' : m)
export { Chip }

import { useMemo, useState } from 'react'
import { api } from '../api'
import { TYPE_LABEL, locLabel } from '../fmt'
import { useStore } from '../store'
import { CHECKS, type Check, type Fix, type TimelineRow } from '../types'
import { Button, Chip, Dot } from './ui'

const CHECK_LABEL: Record<Check, string> = {
  lint: 'Linter accepts the patch', target_gone: 'Target defect gone in every state', no_new_findings: 'No new defects',
  no_drift: 'Nothing else moved or resized', build: 'Build passes',
}
const TOOL_ICON: Record<string, string> = { read_file: '📄', search: '🔎', edit_file: '✎', reset: '↺', rerender: '⟳', check_css_support: '🌐', finish: '⚑' }

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

function Timeline({ fix }: { fix: Fix }) {
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="timeline">
      <h3 className="mb-2 flex-none text-[11px] font-semibold uppercase tracking-wide text-muted">Agent timeline</h3>
      <ol className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
        {fix.status === 'queued' && <li className="text-xs text-muted">Waiting for the running fix session to finish…</li>}
        {fix.status === 'baseline' && (
          <li className="text-xs text-zinc-300" data-testid="baseline">
            Baseline scan of the unpatched code <span className="tabular-nums text-muted">{fix.baseline.done}/{fix.baseline.total}</span>
            <div className="mt-1 h-1 overflow-hidden rounded bg-line"><div className="h-full bg-sky-500 transition-all" style={{ width: `${fix.baseline.total ? (fix.baseline.done / fix.baseline.total) * 100 : 0}%` }} /></div>
          </li>
        )}
        {fix.timeline.map(r => (
          <li key={r.id} data-testid="timeline-row" data-status={r.status} data-name={r.name}
            className={`rounded-md border px-2 py-1.5 text-xs ${r.status === 'blocked' ? 'border-red-500/50 bg-red-500/10' : r.status === 'fail' ? 'border-amber-500/40 bg-amber-500/5' : 'border-line bg-raised'}`}>
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

function Diffs({ fix }: { fix: Fix }) {
  const tabs = useMemo(() => {
    const t = fix.patches.map((p, i) => ({ id: `e${i}`, label: `Edit ${i + 1}`, blocked: p.lint.length > 0, diff: p.diff, lint: p.lint }))
    if (fix.result?.diff) t.push({ id: 'final', label: fix.result.status === 'verified' ? 'Final patch ✓' : 'Final patch', blocked: false, diff: fix.result.diff, lint: [] })
    return t
  }, [fix.patches, fix.result])
  const [pick, setPick] = useState<string | null>(null)
  const active = tabs.find(t => t.id === pick) ?? tabs[tabs.length - 1]
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="diffs">
      <div className="mb-2 flex flex-none flex-wrap items-center gap-1">
        <h3 className="mr-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Diff</h3>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setPick(t.id)} data-testid="diff-tab" data-blocked={t.blocked}
            className={`rounded-md border px-2 py-0.5 text-[11px] ${active?.id === t.id ? 'border-white/30 bg-white/10 text-white' : 'border-line text-muted hover:text-zinc-200'} ${t.blocked ? '!border-red-500/50 text-red-300' : ''}`}>
            {t.label}{t.blocked ? ' ✗' : ''}
          </button>
        ))}
      </div>
      {!active
        ? <p className="text-xs text-muted">The first edit appears here.</p>
        : (
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-line bg-black/30 font-mono text-[11px] leading-5" data-testid="diff">
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

function BeforeAfter({ fix, before, after }: { fix: Fix; before?: string; after?: string }) {
  const [x, setX] = useState(50)
  if (!before || !after) {
    return (
      <div className="grid h-32 place-items-center rounded-md border border-dashed border-line text-xs text-muted" data-testid="before-after-empty">
        {fix.status === 'verifying' ? 'Re-rendering the patched page…' : 'Before / after appears once the patch is verified'}
      </div>
    )
  }
  return (
    <div data-testid="before-after">
      <div className="relative mx-auto aspect-[3/4] max-h-52 overflow-hidden rounded-md border border-line bg-white" style={{ ['--x' as string]: `${x}%` }}>
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

function Grid({ fix, states }: { fix: Fix; states: string[] }) {
  const parsed = states.map(k => { const [, w, theme, stress] = k.split('|'); return { key: k, w: Number(w), row: `${theme} · ${stress === 'pseudo' ? 'pseudo-loc' : 'normal'}` } })
  const widths = [...new Set(parsed.map(p => p.w))].sort((a, b) => a - b)
  const rows = [...new Set(parsed.map(p => p.row))]
  const cell = (row: string, w: number) => parsed.find(p => p.row === row && p.w === w)
  return (
    <div data-testid="grid" className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0.5 text-[10px]">
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
                    className={`h-5 min-w-6 rounded text-center ${v === undefined ? 'bg-[#1d222d]' : v ? 'bg-emerald-500/70' : 'bg-red-500/80'}`}>
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

function Proof({ fix }: { fix: Fix }) {
  const run = useStore(s => s.run)
  const finding = useStore(s => s.findings[fix.key])
  const states = useStore(s => s.states)
  const r = fix.result
  const verified = r?.status === 'verified'

  const stateKeys = useMemo(() => {
    if (r?.states?.length) return r.states
    if (!run) return []
    const route = Object.values(states).find(s => s.key === finding?.candidates[0]?.state_key)?.route ?? run.routes[0]
    return run.widths.flatMap(w => run.themes.flatMap(t => run.text_stress.map(s => `${route}|${w}|${t}|${s}|0`)))
  }, [r, run, states, finding])

  // the narrowest state where it failed is the one to show before and after
  const showKey = useMemo(() => {
    const cs = [...(finding?.candidates ?? [])].sort((a, b) => (states[a.state_key]?.width ?? 1e9) - (states[b.state_key]?.width ?? 1e9))
    return cs[0]?.state_key
  }, [finding, states])

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto pr-1" data-testid="proof">
      <h3 className="-mb-1 flex-none text-[11px] font-semibold uppercase tracking-wide text-muted">Proof</h3>
      <div>
        <div className="mb-1 text-[11px] text-muted">Re-rendered across the matrix (widths × themes × text) — green means the defect is gone</div>
        <Grid fix={fix} states={stateKeys} />
      </div>
      <ul className="space-y-1" data-testid="checklist">
        {CHECKS.map(c => {
          const v = fix.checks[c]
          return (
            <li key={c} data-testid="check" data-check={c} data-state={v === undefined ? 'pending' : v ? 'ok' : 'fail'} className="flex items-center gap-2 text-xs">
              <span className={`grid h-4 w-4 flex-none place-items-center rounded-full text-[10px] ${v === undefined ? 'border border-line text-transparent' : v ? 'bg-emerald-500/80 text-black' : 'bg-red-500 text-white'}`}>{v ? '✓' : v === false ? '✗' : '·'}</span>
              <span className={v === false ? 'font-medium text-red-300' : v ? 'text-zinc-200' : 'text-muted'}>{CHECK_LABEL[c]}</span>
            </li>
          )
        })}
      </ul>
      <div className="flex flex-none items-center gap-2">
        {verified
          ? <a href={api.patchUrl(fix.id)} download data-testid="export" className="inline-flex h-7 items-center rounded-md bg-emerald-500 px-3 text-xs font-semibold text-black hover:bg-emerald-400">Export .patch</a>
          : <Button disabled data-testid="export" title="Only a patch the verifier passed is exported">Export .patch</Button>}
        {r && !verified && <span className="text-[11px] text-red-300" data-testid="not-verified">Not verified: nothing is shown as fixed.</span>}
      </div>
      {r?.verification && r.verification.notes.length > 0 && (
        <pre className="max-h-24 overflow-auto rounded-md border border-red-500/30 bg-red-500/5 p-2 text-[10px] text-red-200" data-testid="notes">{r.verification.notes.join('\n')}</pre>
      )}
      {r?.verification && (r.verification.new_findings.length > 0 || r.verification.drifted.length > 0) && (
        <div className="text-[11px] text-amber-300" data-testid="regressions">
          {r.verification.new_findings.length > 0 && <div>New defects: {r.verification.new_findings.join(', ')}</div>}
          {r.verification.drifted.length > 0 && <div>Moved or resized: {r.verification.drifted.join(', ')}</div>}
        </div>
      )}
      <BeforeAfter fix={fix} before={showKey ? r?.before_shots?.[showKey] : undefined} after={showKey ? r?.verification?.shots?.[showKey] : undefined} />
    </div>
  )
}

const STATUS_CHIP: Record<Fix['status'], { tone: 'zinc' | 'blue' | 'green' | 'red' | 'amber'; text: string }> = {
  queued: { tone: 'zinc', text: 'queued' }, baseline: { tone: 'blue', text: 'baseline scan' }, working: { tone: 'blue', text: 'working' },
  verifying: { tone: 'blue', text: 'verifying' }, verified: { tone: 'green', text: 'verified' }, failed: { tone: 'red', text: 'not verified' },
  budget: { tone: 'amber', text: 'budget reached' }, gave_up: { tone: 'amber', text: 'gave up' }, error: { tone: 'red', text: 'error' },
}

export function FixDrawer() {
  const fixId = useStore(s => s.fixId)
  const fix = useStore(s => (s.fixId ? s.fixes[s.fixId] : undefined))
  const finding = useStore(s => (fix ? s.findings[fix.key] : undefined))
  const set = useStore(s => s.set)
  if (!fix) return null
  const chip = STATUS_CHIP[fix.status]
  const modelName = fix.model.includes('wonder') ? 'Wonder' : fix.model.includes('spark') ? 'Spark' : fix.model

  return (
    <section className="flex h-[45%] min-h-[260px] flex-none flex-col border-t border-line bg-panel shadow-[0_-8px_24px_rgba(0,0,0,0.35)]" data-testid="drawer" data-fix={fixId}>
      <header className="flex flex-none items-center gap-2 border-b border-line px-4 py-2">
        <span className="text-sm font-semibold">Fix</span>
        <span className="text-xs text-zinc-300">{finding ? (TYPE_LABEL[finding.type] ?? finding.type) : fix.key}</span>
        {finding?.locs[0] && <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[11px] text-sky-300">{locLabel(finding.locs[0])}</code>}
        <Chip tone={chip.tone} className="font-semibold" title="">{<span data-testid="fix-status">{chip.text}</span>}</Chip>
        <Chip tone="violet" title="The model that wrote the patch" ><span data-testid="fix-model">{modelName}</span></Chip>
        {fix.fallback && <Chip tone="amber" title={`${fix.fallback.from} was unavailable`}><span data-testid="fallback">fallback from Wonder</span></Chip>}
        {fix.result && <span className="text-[11px] text-muted">{fix.result.turns} turns · {fix.result.tokens.toLocaleString()} tokens</span>}
        {fix.result?.citations.map(c => <a key={c} href={c} target="_blank" rel="noreferrer" className="max-w-40 truncate text-[11px] text-sky-400 underline" title={c}>source</a>)}
        <button onClick={() => set({ drawer: false })} className="ml-auto text-muted hover:text-white" aria-label="close" data-testid="close-drawer">✕</button>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(240px,0.8fr)_minmax(0,1.4fr)_minmax(300px,1fr)] gap-4 p-3">
        <Timeline fix={fix} />
        <Diffs fix={fix} />
        <Proof fix={fix} />
      </div>
    </section>
  )
}

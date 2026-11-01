import { Link } from 'react-router-dom'
import { SEVERITY_COLOR, STATUS_HELP, STATUS_LABEL, TYPE_EXPLAIN, TYPE_LABEL, locLabel, widthRange } from '../fmt'
import { paths } from '../paths'
import { counts, severityOf, sortedFindings, useStore } from '../store'
import { STATUSES, type Finding, type Status } from '../types'
import { RunHeader } from '../components/RunHeader'
import { isBusy } from '../components/fix'
import { Chip, Dot, Empty } from '../components/ui'

const TILE_TONE: Record<Status, string> = { confirmed: 'text-red-300', needs_review: 'text-amber-300', dismissed: 'text-zinc-400', not_observable: 'text-zinc-500' }

function FixBadge({ f }: { f: Finding }) {
  const fix = useStore(s => Object.values(s.fixes).filter(x => x.key === f.key).at(-1))
  if (!fix) return null
  if (fix.status === 'verified') return <Chip tone="green" className="flex-none whitespace-nowrap font-medium">Fixed ✓</Chip>
  if (isBusy(fix)) return <Chip tone="blue">Fixing…</Chip>
  return <Chip tone="red">Fix not verified</Chip>
}

function FindingRow({ f, runId }: { f: Finding; runId: string }) {
  return (
    <li>
      <Link to={paths.finding(runId, f.key)} data-testid="finding-row" data-key={f.key}
        className="flex items-center gap-4 rounded-xl border border-line bg-panel px-4 py-3 transition-colors hover:border-zinc-500">
        <Dot color={SEVERITY_COLOR[severityOf(f)] ?? '#64748b'} size={10} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[14px] font-semibold">{TYPE_LABEL[f.type] ?? f.type}</span>
            <FixBadge f={f} />
          </div>
          <p className="mt-0.5 truncate text-xs text-muted">{f.triage?.what_the_user_sees ?? TYPE_EXPLAIN[f.type]}</p>
        </div>
        <span className="hidden w-28 flex-none text-right text-xs tabular-nums text-zinc-400 sm:block" title="Screen widths where it happens">{widthRange(f.widths)}</span>
        {f.locs[0]
          ? <code className="hidden w-44 flex-none truncate rounded bg-black/30 px-1.5 py-0.5 font-mono text-[11px] text-sky-300 md:block" title={f.locs.join('\n')}>{locLabel(f.locs[0])}</code>
          : <span className="hidden w-44 flex-none px-1.5 text-[11px] text-muted md:block">no source link</span>}
        <span className="flex-none text-muted">›</span>
      </Link>
    </li>
  )
}

/** The run's findings, one status at a time, most severe first. */
export function RunPage() {
  const runId = useStore(s => s.runId)
  const run = useStore(s => s.run)
  const findings = useStore(s => s.findings)
  const tab = useStore(s => s.tab)
  const set = useStore(s => s.set)
  const c = counts(findings)
  const list = sortedFindings(findings, tab)

  return (
    <div className="mx-auto max-w-5xl p-4 md:p-8" data-testid="run-page">
      <RunHeader />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4" role="tablist" data-testid="status-tiles">
        {STATUSES.map(s => (
          <button key={s} onClick={() => set({ tab: s })} role="tab" aria-selected={tab === s} data-testid={`tab-${s}`} data-active={tab === s} title={STATUS_HELP[s]}
            className={`rounded-xl border p-3 text-left transition-colors ${tab === s ? 'border-sky-500/60 bg-sky-500/10' : 'border-line bg-panel hover:border-zinc-600'}`}>
            <div className={`text-2xl font-semibold tabular-nums ${TILE_TONE[s]}`} data-testid={`count-${s}`}>{c[s]}</div>
            <div className="text-xs text-zinc-300">{STATUS_LABEL[s]}</div>
          </button>
        ))}
      </div>
      <p className="mb-3 text-xs text-muted" data-testid="status-help">{STATUS_HELP[tab]}</p>
      {!run || !runId ? null : list.length === 0 ? (
        <Empty title={run.status === 'running' ? 'Looking…' : `Nothing ${STATUS_LABEL[tab].toLowerCase()}`} icon={run.status === 'running' ? '⋯' : '✓'} testid="findings-empty">
          {run.status === 'running' ? 'Findings appear here as screens are checked.' : tab === 'confirmed' ? 'No confirmed layout bugs in this scan.' : 'Nothing in this group.'}
        </Empty>
      ) : (
        <ul className="space-y-2" data-testid="findings">{list.map(f => <FindingRow key={f.key} f={f} runId={runId} />)}</ul>
      )}
    </div>
  )
}

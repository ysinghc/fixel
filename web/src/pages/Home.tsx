import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, targetOf, type RunDetail, type RunRow } from '../api'
import { paths } from '../paths'
import type { BenchList } from '../types'
import { ago, RunStatusChip } from '../components/RunBits'
import { Card, Icon, PageHeader, Progress } from '../components/ui'

interface Todo { to: string; text: string; detail: string; progress?: [number, number]; testid: string }

/** What needs doing next, and the three jobs one click away. */
export function Home() {
  const [runs, setRuns] = useState<RunRow[] | null>(null)
  const [latest, setLatest] = useState<RunDetail | null>(null)
  const [bench, setBench] = useState<BenchList | null>(null)

  useEffect(() => {
    api.runs().then(rs => {
      const scans = rs.filter(r => r.kind === 'scan')
      setRuns(scans)
      if (scans[0]) api.run(scans[0].id).then(setLatest).catch(() => {})
    }).catch(() => setRuns([]))
    api.bench().then(setBench).catch(() => setBench(null))
  }, [])

  // unfinished work first (the Zeigarnik effect): it is what people come back for
  const todos: Todo[] = []
  for (const r of runs ?? []) {
    if (r.status === 'running') todos.push({ to: paths.run(r.id), text: `A scan of ${targetOf(r.config.config)} is running`, detail: 'Watch it fill in', testid: 'todo-running' })
  }
  if (latest && latest.status !== 'running') {
    const verified = new Set(latest.fixes.filter(f => f.status === 'verified').map(f => f.key))
    const open = latest.findings.filter(f => f.status === 'confirmed' && !verified.has(f.key)).length
    if (open) todos.push({ to: paths.run(latest.id), text: `${open} confirmed finding${open === 1 ? '' : 's'} not fixed yet`, detail: `in ${targetOf(latest.config.config)}, ${ago(latest.created)}`, testid: 'todo-findings' })
  }
  for (const b of bench?.runs ?? []) {
    const total = b.queue ?? b.n_cases
    if (b.split === 'test' && b.labelled < total) {
      todos.push({ to: paths.label, text: `${total - b.labelled} screens left to label`, detail: 'The benchmark headline waits on these', progress: [b.labelled, total], testid: 'todo-labels' })
      break
    }
  }

  const confirmed = latest?.findings.filter(f => f.status === 'confirmed').length ?? 0
  const labelRun = bench?.runs.find(b => b.split === 'test') ?? bench?.runs[0]
  const left = labelRun ? (labelRun.queue ?? labelRun.n_cases) - labelRun.labelled : null

  return (
    <div className="mx-auto max-w-5xl p-4 md:p-8" data-testid="home">
      <PageHeader title="What would you like to do?" subtitle="Fixel renders your pages at every screen width, finds layout bugs in the pixels, and fixes them with proof." />

      <div className="grid gap-4 md:grid-cols-3">
        <ActionCard to={paths.scan} icon="scan" title="Scan an app" primary testid="action-scan"
          text="Render every page at every width and theme, then find what breaks." />
        <ActionCard to={latest ? paths.run(latest.id) : paths.runs} icon="results" title="Review findings" testid="action-review"
          text={latest ? `${confirmed} confirmed in the latest scan of ${targetOf(latest.config.config)}.` : 'No scans yet. Start one first.'} />
        <ActionCard to={paths.label} icon="label" title="Label screens" testid="action-label"
          text={left === null ? 'Nothing to label until a benchmark has run.' : left > 0 ? `${left} screens waiting for a blind yes or no.` : 'Everything is labelled.'} />
      </div>

      {todos.length > 0 && (
        <Card title="Continue where you left off" className="mt-6" testid="todos">
          <ul className="divide-y divide-line">
            {todos.map(t => (
              <li key={t.testid}>
                <Link to={t.to} data-testid={t.testid} className="-mx-2 flex items-center gap-4 rounded-lg px-2 py-3 hover:bg-white/5">
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-medium">{t.text}</div>
                    <div className="text-xs text-muted">{t.detail}</div>
                    {t.progress && <div className="mt-2 max-w-sm"><Progress value={t.progress[0]} total={t.progress[1]} label="Task progress" /></div>}
                  </div>
                  <span className="text-sm text-sky-300">→</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Recent scans" className="mt-6" testid="recent" aside={runs && runs.length > 0 ? <Link to={paths.runs} className="text-xs text-sky-300 hover:underline">All results →</Link> : null}>
        {runs === null ? <div className="skeleton h-16 rounded-lg" /> : runs.length === 0 ? (
          <p className="py-4 text-sm text-muted" data-testid="no-scans">No scans yet. <Link to={paths.scan} className="text-sky-300 underline underline-offset-2 hover:text-sky-200">Start your first scan</Link>; it takes about a minute on the demo app.</p>
        ) : (
          <ul className="divide-y divide-line">
            {runs.slice(0, 5).map(r => (
              <li key={r.id}>
                <Link to={paths.run(r.id)} className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-white/5" data-testid="recent-run">
                  <span className="w-40 truncate text-[13px] font-medium">{targetOf(r.config.config)}</span>
                  <RunStatusChip status={r.status} />
                  <span className="text-xs text-muted">{r.summary.counts ? `${r.summary.counts.confirmed ?? 0} confirmed` : ''}</span>
                  <span className="ml-auto text-xs text-muted">{ago(r.created)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function ActionCard({ to, icon, title, text, primary, testid }: { to: string; icon: string; title: string; text: string; primary?: boolean; testid: string }) {
  return (
    <Link to={to} data-testid={testid}
      className={`group flex flex-col gap-3 rounded-xl border p-5 transition-colors ${primary ? 'border-sky-500/50 bg-sky-500/10 hover:bg-sky-500/15' : 'border-line bg-panel hover:border-zinc-600'}`}>
      <span className={`grid h-10 w-10 place-items-center rounded-lg ${primary ? 'bg-sky-400 text-black' : 'bg-raised text-zinc-300'}`}><Icon name={icon} /></span>
      <div>
        <div className="text-[15px] font-semibold">{title} <span className="opacity-0 transition-opacity group-hover:opacity-100">→</span></div>
        <p className="mt-1 text-xs leading-5 text-muted">{text}</p>
      </div>
    </Link>
  )
}

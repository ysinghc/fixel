import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { STATUS_HELP, STATUS_LABEL, TYPE_EXPLAIN, TYPE_LABEL, geometryText, locLabel, pixelsText, representative, widthRange } from '../fmt'
import { paths } from '../paths'
import { sortedFindings, useStore } from '../store'
import type { Finding } from '../types'
import { FIX_STATUS, isBusy } from '../components/fix'
import { Viewer } from '../components/Viewer'
import { Button, ButtonLink, Chip, Empty, Kbd } from '../components/ui'

const STATUS_TONE = { confirmed: 'red', needs_review: 'amber', dismissed: 'zinc', not_observable: 'zinc' } as const

function Evidence({ label, value, text, tone, testid }: { label: string; value: ReactNode; text: string; tone: 'amber' | 'teal' | 'blue' | 'zinc'; testid: string }) {
  const bar = { amber: 'bg-amber-400', teal: 'bg-teal-400', blue: 'bg-sky-400', zinc: 'bg-zinc-500' }[tone]
  return (
    <li className="relative rounded-lg border border-line bg-raised py-2.5 pl-4 pr-3" data-testid={testid}>
      <span className={`absolute inset-y-2 left-1.5 w-1 rounded-full ${bar}`} />
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-0.5 text-[13px] font-medium text-zinc-100">{value}</div>
      <p className="mt-0.5 text-[11px] leading-4 text-muted">{text}</p>
    </li>
  )
}

function sparkLine(f: Finding, hasModels: boolean, running: boolean): { value: string; text: string; tone: 'blue' | 'zinc' } {
  const t = f.triage
  if (t) return { value: `${t.verdict.replace('_', ' ')} · ${Math.round(t.confidence * 100)}% sure`, text: 'Spark 1.3 looked at the screenshot. It can dismiss a finding or ask for review, never create one.', tone: 'blue' }
  if (f.status === 'dismissed') return { value: 'dismissed by code', text: 'The elements can be scrolled apart, so the overlap is by design.', tone: 'zinc' }
  if (!hasModels) return { value: 'Spark unavailable — geometry and pixels only', text: 'Models were off for this scan, so no model looked at it.', tone: 'zinc' }
  return { value: running ? 'pending…' : 'not asked', text: 'Spark describes confirmed findings only.', tone: 'zinc' }
}

/** One finding: the screenshot with it outlined, why Fixel believes it, where in the code, and one action. */
export function FindingPage() {
  const { run: runParam = '', key = '' } = useParams()
  const navigate = useNavigate()
  const runId = useStore(s => s.runId)
  const run = useStore(s => s.run)
  const findings = useStore(s => s.findings)
  const states = useStore(s => s.states)
  const f = findings[key]
  const allFixes = useStore(s => s.fixes)                    // a stable map; filtering inside the selector would loop
  const fixes = useMemo(() => Object.values(allFixes).filter(x => x.key === key), [allFixes, key])
  const label = useStore(s => s.labels[key])
  const [err, setErr] = useState('')
  const [starting, setStarting] = useState(false)

  useEffect(() => { useStore.getState().selectFinding(key) }, [key, runId])
  useEffect(() => () => useStore.getState().set({ stateKey: null, findingKey: null }), [])

  const list = f ? sortedFindings(findings, f.status) : []
  const i = list.findIndex(x => x.key === key)
  const prev = i > 0 ? list[i - 1] : undefined
  const next = i >= 0 && i < list.length - 1 ? list[i + 1] : undefined
  const lastFix = fixes.at(-1)
  const busy = isBusy(lastFix)
  const canFix = f?.status === 'confirmed' && run?.status !== 'running' && !busy

  const startFix = async () => {
    setErr(''); setStarting(true)
    try {
      const { fix_id } = await api.fix(runParam, key)
      navigate(paths.fix(runParam, fix_id))
    } catch (e) { setErr((e as Error).message); setStarting(false) }
  }
  const notDefect = async () => {
    setErr('')
    try { await api.label(runParam, key, 'no_visible_defect'); useStore.getState().set({ labels: { ...useStore.getState().labels, [key]: 'no_visible_defect' } }) }
    catch (e) { setErr((e as Error).message) }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName) || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'j' && next) navigate(paths.finding(runParam, next.key))
      else if (e.key === 'k' && prev) navigate(paths.finding(runParam, prev.key))
      else if (e.key === 'f' && canFix) void startFix()
      else if (e.key === 'Escape') navigate(paths.run(runParam))
      else if (['1', '2', '3', '4'].includes(e.key)) useStore.getState().toggleLayer((['dom', 'sam', 'candidates', 'findings'] as const)[Number(e.key) - 1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!f) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        {run && run.status !== 'running' && Object.keys(findings).length > 0
          ? <Empty title="This finding is not in this scan" testid="finding-missing" action={<ButtonLink to={paths.run(runParam)} kind="primary">All findings</ButtonLink>} />
          : <div className="skeleton h-96 rounded-xl" data-testid="finding-loading" />}
      </div>
    )
  }

  const ev = f.evidence[representative(f, states).index]
  const spark = sparkLine(f, !!run?.models, run?.status === 'running')
  const sentence = f.triage?.what_the_user_sees ?? TYPE_EXPLAIN[f.type]

  return (
    <div className="flex h-full flex-col px-6 pb-4 pt-5" data-testid="finding-page" data-key={key}>
      <header className="flex flex-none flex-wrap items-end gap-4 pb-4">
        <div className="min-w-0 flex-1">
          <Link to={paths.run(runParam)} className="text-xs text-muted hover:text-zinc-200" data-testid="back">← All findings</Link>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight" data-testid="finding-title">{TYPE_LABEL[f.type] ?? f.type}</h1>
            <Chip tone={STATUS_TONE[f.status]} title={STATUS_HELP[f.status]}>{STATUS_LABEL[f.status]}</Chip>
            <Chip tone="zinc" title="Screen widths where it happens" className="tabular-nums">{widthRange(f.widths)}</Chip>
          </div>
          <p className="mt-1 max-w-3xl text-sm text-zinc-300" data-testid="sentence">{sentence}</p>
        </div>
        <div className="flex flex-none items-center gap-2">
          <Button onClick={notDefect} disabled={!!label} data-testid="mark-wrong" title="Record that a person sees no defect here. It becomes a human label.">{label ? 'Marked: not a defect' : 'Not a defect'}</Button>
          {lastFix && (lastFix.status === 'verified' || busy)
            ? <ButtonLink to={paths.fix(runParam, lastFix.id)} kind={lastFix.status === 'verified' ? 'success' : 'primary'} size="md" data-testid="view-fix">{lastFix.status === 'verified' ? 'Fixed ✓ View the fix' : 'Fixing… watch it'}</ButtonLink>
            : f.status === 'confirmed' && (
              <Button kind="primary" size="md" onClick={startFix} disabled={!canFix || starting} data-testid="fix-button"
                title={run?.status === 'running' ? 'Wait for the scan to finish' : 'Repair it in an isolated copy of the code and check it on every screen'}>
                {starting ? 'Starting…' : lastFix ? 'Try the fix again' : 'Fix this'} <Kbd>f</Kbd>
              </Button>
            )}
        </div>
      </header>
      {err && <div className="mb-3 flex-none rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200" data-testid="card-error">{err}</div>}

      <div className="flex min-h-0 flex-1 gap-5">
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-line bg-ink">
          <Viewer />
        </div>
        <aside className="flex w-[340px] flex-none flex-col gap-4 overflow-y-auto" data-testid="finding-side">
          <section>
            <h2 className="mb-2 text-[13px] font-semibold">Why Fixel believes it</h2>
            <ul className="space-y-2" data-testid="chips">
              <Evidence testid="ev-geometry" label="Geometry" tone="amber" value={geometryText(f)} text="Measured from the page's element boxes." />
              <Evidence testid="ev-pixels" label="Pixels" tone="teal" value={pixelsText(f, ev)} text="Hide one element and count the pixels that change; SAM checks what is painted." />
              <Evidence testid="ev-spark" label="Spark" tone={spark.tone} value={spark.value} text={spark.text} />
            </ul>
          </section>
          <section>
            <h2 className="mb-2 text-[13px] font-semibold">Where in the code</h2>
            {f.locs.length
              ? <ul className="space-y-1">{f.locs.map(l => <li key={l}><code className="block truncate rounded bg-black/30 px-2 py-1 font-mono text-[12px] text-sky-300" title={l}>{locLabel(l)}</code></li>)}</ul>
              : <p className="text-xs text-muted">No source location: this app was not built with Fixel's source map plugin.</p>}
          </section>
          {fixes.length > 0 && (
            <section data-testid="fix-history">
              <h2 className="mb-2 text-[13px] font-semibold">Fix attempts</h2>
              <ul className="space-y-1">
                {fixes.map((x, n) => (
                  <li key={x.id}><Link to={paths.fix(runParam, x.id)} className="flex items-center gap-2 rounded-lg border border-line bg-raised px-3 py-2 text-xs hover:border-zinc-500">
                    Attempt {n + 1}<Chip tone={FIX_STATUS[x.status].tone} className="ml-auto">{FIX_STATUS[x.status].text}</Chip>
                  </Link></li>
                ))}
              </ul>
            </section>
          )}
          <nav className="mt-auto flex items-center gap-2 border-t border-line pt-3 text-xs" data-testid="pager">
            <Button onClick={() => prev && navigate(paths.finding(runParam, prev.key))} disabled={!prev} data-testid="prev">← Previous <Kbd>k</Kbd></Button>
            <span className="flex-1 text-center tabular-nums text-muted">{i + 1} of {list.length} {STATUS_LABEL[f.status].toLowerCase()}</span>
            <Button onClick={() => next && navigate(paths.finding(runParam, next.key))} disabled={!next} data-testid="next">Next <Kbd>j</Kbd> →</Button>
          </nav>
        </aside>
      </div>
    </div>
  )
}

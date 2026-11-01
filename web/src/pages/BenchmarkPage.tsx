import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import { paths } from '../paths'
import type { BenchList, BenchMetrics, Rate } from '../types'
import { LayerChart } from '../components/LayerChart'
import { SplitChip } from '../components/RunBits'
import { ButtonLink, Card, Chip, Empty, PageHeader, Tabs } from '../components/ui'

const LEVEL: Record<string, string> = { geometry: 'Geometry', diff: '+ Pixel diff', sam: '+ SAM 3.1', spark: '+ Spark triage' }
const KNOWN = [['opaque_banner', 'A banner covers a button'], ['ghost_banner', 'A see-through-to-clicks banner covers a button (known gap)'],
  ['badge_overlap', 'A badge on a button: must be dismissed'], ['open_dropdown', 'An open menu: must be dismissed'], ['invisible_overlap', 'Invisible text: must be not visible']] as const
type Tab = 'summary' | 'human' | 'known' | 'injected' | 'details'
type Measure = 'controls' | 'agreement' | 'precision' | 'recall'

function Pct({ r }: { r: Rate | null | undefined }) {
  if (!r) return <span className="text-muted">–</span>
  return <span title={`${r.k} of ${r.n} · 95% interval ${Math.round(r.lo * 100)}–${Math.round(r.hi * 100)}%`}><span className="tabular-nums text-zinc-100">{Math.round(r.p * 100)}%</span> <span className="text-[11px] tabular-nums text-muted">{r.k}/{r.n}</span></span>
}

function Table({ head, rows, testid }: { head: string[]; rows: ReactNode[][]; testid?: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line" data-testid={testid}>
      <table className="w-full text-left text-[13px]">
        <thead className="bg-raised text-[11px] uppercase tracking-wide text-muted"><tr>{head.map(h => <th key={h} className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-line">{r.map((c, j) => <td key={j} className="px-4 py-2.5 text-zinc-300">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

function Stat({ label, r, help, testid }: { label: string; r: Rate | null | undefined; help: string; testid: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-4" data-testid={testid}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums">{r ? `${Math.round(r.p * 100)}%` : '–'}</div>
      <div className="mt-1 text-[11px] text-muted">{r ? `${r.k} of ${r.n} · 95% interval ${Math.round(r.lo * 100)}–${Math.round(r.hi * 100)}%` : help}</div>
    </div>
  )
}

/** Measured results only: a summary first, then one topic per tab. Nothing is drawn that a run has not produced. */
export function BenchmarkPage() {
  const [list, setList] = useState<BenchList | null>(null)
  const [run, setRun] = useState('')
  const [m, setM] = useState<BenchMetrics | null>(null)
  const [tab, setTab] = useState<Tab>('summary')
  const [measure, setMeasure] = useState<Measure>('controls')
  const [error, setError] = useState('')

  useEffect(() => {
    api.bench().then(b => { setList(b); const pick = b.runs.find(r => r.split === 'test') ?? b.runs[0]; if (pick) setRun(r => r || pick.run) })
      .catch(() => setList({ available: false, reason: 'the API is not reachable', runs: [] }))
  }, [])
  useEffect(() => {
    if (!run) return
    let current = true                                    // a slower answer for the previous run must not overwrite this one
    setM(null)
    api.benchMetrics(run).then(x => { if (current) setM(x) }).catch(e => { if (current) setError(String(e.message)) })
    return () => { current = false }
  }, [run])
  useEffect(() => { if (m?.human) setMeasure('precision') }, [m?.human])

  if (!list) return <div className="mx-auto max-w-5xl p-4 md:p-8" data-testid="bench"><div className="skeleton h-40 rounded-xl" /></div>
  if (!list.available) {
    return (
      <div className="mx-auto max-w-5xl p-4 md:p-8" data-testid="bench">
        <PageHeader title="Benchmark" subtitle="How well Fixel finds layout bugs, measured against people and known answers." />
        <Empty title="Not available yet" icon="▦" testid="bench-none">
          <p>{(list.reason ?? 'no benchmark has been run').split('`').map((part, i) => i % 2 ? <code key={i} className="whitespace-nowrap rounded bg-black/40 px-1 py-0.5 font-mono text-xs text-zinc-300">{part}</code> : part)}</p>
          <pre className="mt-3 rounded-lg bg-black/40 p-2 text-left text-xs text-zinc-300">fixel bench run --split dev --mutated 60 --clean 20</pre>
          <p className="mt-3 text-xs">No number is shown until it is measured.</p>
        </Empty>
      </div>
    )
  }

  const levels = m?.levels ?? []
  const last = levels[levels.length - 1]
  const h = m?.human
  const runRow = list.runs.find(r => r.run === run)
  const left = runRow ? (runRow.queue ?? runRow.n_cases) - runRow.labelled : 0
  const chartRows = levels.map(lv => ({
    level: lv,
    r: measure === 'controls' ? m?.construction[lv]?.controls ?? null : measure === 'agreement' ? m?.injected_agreement[lv]?._all ?? null
      : measure === 'precision' ? h?.[lv]?.precision ?? null : h?.[lv]?.recall ?? null,
  }))
  const MEASURES: { value: Measure; label: string; needsLabels?: boolean }[] = [
    { value: 'precision', label: 'Precision', needsLabels: true }, { value: 'recall', label: 'Recall', needsLabels: true },
    { value: 'controls', label: 'Known answers' }, { value: 'agreement', label: 'Injected defects found' },
  ]

  return (
    <div className="mx-auto max-w-5xl p-4 md:p-8" data-testid="bench">
      <PageHeader title="Benchmark" subtitle="How well Fixel finds layout bugs, measured against blind human labels and cases with known answers."
        actions={(
          <select value={run} onChange={e => setRun(e.target.value)} data-testid="bench-run" className="h-9 rounded-lg border border-line bg-raised px-2 text-xs">
            {list.runs.map(r => <option key={r.run} value={r.run}>{r.run}{r.split ? ` (${r.split})` : ''}</option>)}
          </select>
        )} />
      {error && <p className="mb-3 text-xs text-red-300">{error}</p>}
      {!m ? <div className="skeleton h-60 rounded-xl" /> : (
        <>
          <div className={`mb-5 flex flex-wrap items-center gap-3 rounded-xl border p-4 ${m.headline ? 'border-emerald-500/40 bg-emerald-500/10' : 'border-amber-500/30 bg-amber-500/5'}`} data-testid="headline">
            {m.headline ? <Chip tone="green">headline result</Chip> : <Chip tone="amber">not a headline result</Chip>}
            <span className="text-sm text-zinc-200">{m.headline ? 'Test split, with blind human labels.' : m.meta.split !== 'test' ? 'Development split: these numbers tune Fixel and are never a result.' : 'Needs human labels before it can be a headline.'}</span>
            <SplitChip split={m.meta.split === 'dev' ? 'development' : m.meta.split} />
            {m.meta.mode === 'replay' && <Chip tone="amber">REPLAY: answers from the cache</Chip>}
            <span className="ml-auto text-[11px] text-muted">{m.n_mutated} injected + {m.n_clean} unmodified screens</span>
          </div>

          <Tabs value={tab} onChange={setTab} testid="bench-tabs" items={[
            { value: 'summary', label: 'Summary', testid: 'btab-summary' },
            { value: 'human', label: 'Human labels', count: m.labels.n, testid: 'btab-human' },
            { value: 'known', label: 'Known answers', testid: 'btab-known' },
            { value: 'injected', label: 'Injected defects', testid: 'btab-injected' },
            { value: 'details', label: 'Cost and caveats', count: m.caveats.length, testid: 'btab-details' },
          ]} />

          {tab === 'summary' && (
            <div className="space-y-5" data-testid="summary">
              {h ? (
                <div className="grid gap-3 md:grid-cols-3">
                  <Stat testid="stat-precision" label="Precision, with every layer on" r={h[last]?.precision} help="" />
                  <Stat testid="stat-recall" label="Recall, with every layer on" r={h[last]?.recall} help="" />
                  <Stat testid="stat-fp" label="False positives on unmodified pages" r={h[last]?.clean_false_positive_rate} help="No unmodified screen labelled 'no defect' yet." />
                </div>
              ) : (
                <Card testid="no-labels" className="flex flex-wrap items-center gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium">No human labels for this run yet</div>
                    <p className="text-xs text-muted">Precision and recall need people to say which screens really show a defect. {left > 0 ? `${left} screens are waiting.` : ''}</p>
                  </div>
                  <ButtonLink to={paths.label} kind="primary" size="md" data-testid="go-label">Label screens</ButtonLink>
                </Card>
              )}
              <Card title="What each layer adds" aside={(
                <div className="flex gap-1" role="radiogroup" data-testid="measure">
                  {MEASURES.filter(x => !x.needsLabels || h).map(x => (
                    <button key={x.value} onClick={() => setMeasure(x.value)} role="radio" aria-checked={measure === x.value} data-testid={`measure-${x.value}`}
                      className={`rounded-md px-2 py-1 text-[11px] ${measure === x.value ? 'bg-sky-500/20 text-sky-100' : 'text-muted hover:text-zinc-200'}`}>{x.label}</button>
                  ))}
                </div>
              )}>
                <p className="mb-3 text-xs text-muted">
                  {measure === 'controls' ? 'Cases with a known answer handled correctly: three kinds of overlap that must not be reported as bugs.'
                    : measure === 'agreement' ? 'How often Fixel reported the kind of defect that was injected. A tuning signal, not accuracy.'
                    : measure === 'precision' ? 'Of the screens Fixel flagged, the share a person also called a defect.'
                    : 'Of the screens a person called a defect, the share Fixel flagged.'} Each bar adds one layer to the one above; the whisker is the 95% interval.
                </p>
                <LayerChart rows={chartRows} testid="layer-chart" />
              </Card>
            </div>
          )}

          {tab === 'human' && (
            <div data-testid="human">
              {!h ? (
                <Empty title="No human labels yet" icon="✎" testid="no-labels-tab" action={<ButtonLink to={paths.label} kind="primary" size="md">Label screens</ButtonLink>}>
                  Each screen is shown blind: whether it was changed, and what Fixel found, are hidden.
                </Empty>
              ) : (
                <>
                  <p className="mb-3 text-xs text-muted">{m.labels.n} labelled: {m.labels.visible_defect} visible defect, {m.labels.no_visible_defect} no defect, {m.labels.unsure} unsure (left out). A screen counts as flagged when Fixel confirms at least one finding on it.</p>
                  <Table testid="human-table" head={['Detection layers', 'Precision', 'Recall', 'False positives on unmodified pages']}
                    rows={levels.map(lv => [LEVEL[lv], <Pct r={h[lv]?.precision} />, <Pct r={h[lv]?.recall} />, <Pct r={h[lv]?.clean_false_positive_rate} />])} />
                </>
              )}
            </div>
          )}

          {tab === 'known' && (
            <div data-testid="construction">
              <p className="mb-3 text-xs text-muted">Cases whose answer is known without running any geometry. The see-through banner paints over a button but clicks pass through it, so hit testing cannot see it: it measures a known gap.</p>
              <Table head={['Case', ...levels.map(l => LEVEL[l])]} rows={KNOWN.map(([op, text]) => [text, ...levels.map(lv => <Pct r={m.construction[lv]?.[op]} />)])} />
            </div>
          )}

          {tab === 'injected' && (
            <div data-testid="agreement">
              <p className="mb-3 text-xs text-muted">Not detection accuracy. Whether Fixel reported the kind of defect that was injected: a regression signal for tuning on the development split. People decide what is really visible.</p>
              <Table head={['Injected defect', ...levels.map(l => LEVEL[l])]}
                rows={[...Object.keys(m.injected_agreement[last] ?? {}).filter(k => !k.startsWith('_')).map(op => [op.replace(/_/g, ' '), ...levels.map(lv => <Pct r={m.injected_agreement[lv]?.[op]} />)]),
                  [<b>All</b>, ...levels.map(lv => <Pct r={m.injected_agreement[lv]?._all} />)],
                  ['…and named the changed element in the code', ...levels.map(lv => <Pct r={m.localization[lv]} />)]]} />
            </div>
          )}

          {tab === 'details' && (
            <div className="space-y-5">
              <Card title="Read these before quoting a number" testid="caveats">
                <ul className="space-y-1.5 text-xs text-amber-200">{m.caveats.map(c => <li key={c}>• {c}</li>)}</ul>
              </Card>
              <Card title="Cost and time" testid="cost">
                <p className="text-xs text-zinc-300">
                  {m.cost.usd != null ? `$${m.cost.usd.toFixed(2)}` : 'n/a'} for {m.n_cases} cases ({m.cost.usd_per_case ?? 'n/a'} per case), {m.cost.seconds_per_case ?? 'n/a'} s per case.
                  Model calls: {m.cost.model_calls ? `${m.cost.model_calls.live} live, ${m.cost.model_calls.cached} from the cache` : 'n/a'}. Seed {m.meta.seed}, code {m.meta.code?.commit ?? '?'}{m.meta.code?.dirty ? ' (with uncommitted changes)' : ''}.
                </p>
              </Card>
              <p className="text-[11px] text-muted">Not measured yet: the fix benchmark (verified-fix rate, revert-equivalence, linter blocks, regressions caught), the triage and fixer model comparisons, and the synthetic and Storybook corpora.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}

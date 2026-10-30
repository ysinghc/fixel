import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { BenchList, BenchMetrics, HumanLevel, Rate } from '../types'
import { Chip } from './ui'

const LEVEL: Record<string, string> = { geometry: 'Geometry', diff: '+ Opacity diff', sam: '+ SAM 3.1', spark: '+ Spark 1.3 triage' }
const OPS_BANNER = [['opaque_banner', 'Opaque banner covers a button'], ['ghost_banner', 'Ghost banner (pointer-events: none)']] as const
const CONTROLS = [['badge_overlap', 'Badge on a button (must be dismissed)'], ['open_dropdown', 'Open menu (must be dismissed)'], ['invisible_overlap', 'Invisible text (must be not observable)']] as const

/** A proportion with its Wilson 95% interval: a bar for the interval, the number, and the counts. */
function RateCell({ r, tone = 'sky' }: { r: Rate | null | undefined; tone?: 'sky' | 'emerald' | 'rose' }) {
  if (!r) return <span className="text-muted">n/a</span>
  const color = { sky: 'bg-sky-400', emerald: 'bg-emerald-400', rose: 'bg-rose-400' }[tone]
  return (
    <div className="min-w-28" title={`${r.k} of ${r.n} · 95% interval ${Math.round(r.lo * 100)}–${Math.round(r.hi * 100)}%`}>
      <div className="flex items-baseline gap-1.5">
        <span className="tabular-nums text-zinc-100">{Math.round(r.p * 100)}%</span>
        <span className="text-[10px] tabular-nums text-muted">{r.k}/{r.n}</span>
      </div>
      <div className="relative mt-1 h-1.5 rounded bg-line">
        <div className={`absolute h-full rounded ${color} opacity-30`} style={{ left: `${r.lo * 100}%`, width: `${(r.hi - r.lo) * 100}%` }} />
        <div className={`absolute top-[-1px] h-2 w-0.5 ${color}`} style={{ left: `${r.p * 100}%` }} />
      </div>
    </div>
  )
}

function Table({ head, rows, testid }: { head: string[]; rows: ReactNode[][]; testid?: string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line" data-testid={testid}>
      <table className="w-full text-left text-xs">
        <thead className="bg-raised text-[11px] uppercase tracking-wide text-muted">
          <tr>{head.map(h => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-line">{r.map((c, j) => <td key={j} className="px-3 py-2 align-top text-zinc-300">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

function Section({ title, note, children, testid }: { title: string; note?: string; children: ReactNode; testid?: string }) {
  return (
    <section className="space-y-2" data-testid={testid}>
      <div><h3 className="text-sm font-semibold">{title}</h3>{note && <p className="text-[11px] leading-4 text-muted">{note}</p>}</div>
      {children}
    </section>
  )
}

/** Measured results only. Nothing is drawn that a benchmark run has not produced. */
export function BenchmarkView() {
  const [list, setList] = useState<BenchList | null>(null)
  const [run, setRun] = useState('')
  const [m, setM] = useState<BenchMetrics | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.bench().then(b => { setList(b); if (b.runs[0]) setRun(r => r || b.runs[0].run) }).catch(() => { setList({ available: false, reason: 'the API is not reachable', runs: [] }) })
  }, [])
  useEffect(() => {
    if (!run) return
    setM(null)
    api.benchMetrics(run).then(setM).catch(e => setError(String(e.message)))
  }, [run])

  if (!list) return <div className="flex-1 p-8 text-sm text-muted" data-testid="bench">Loading…</div>
  if (!list.available) {
    return (
      <div className="grid flex-1 place-items-center p-8" data-testid="bench">
        <div className="max-w-xl space-y-3 rounded-xl border border-line bg-panel p-6">
          <h2 className="text-base font-semibold">Benchmark</h2>
          <p className="text-sm text-zinc-300" data-testid="bench-none">Not available yet: {list.reason ?? 'no benchmark has been run'}.</p>
          <pre className="rounded bg-black/40 p-2 text-xs">fixel bench run --split dev --mutated 60 --clean 20</pre>
          <p className="text-xs text-muted">No figure is shown until it is measured.</p>
        </div>
      </div>
    )
  }

  const h = m?.human
  const levels = m?.levels ?? []
  const toLabel = m ? Math.max(0, (list.runs.find(r => r.run === m.run)?.queue ?? 0) - m.labels.n) : 0
  return (
    <div className="min-h-0 flex-1 overflow-y-auto" data-testid="bench">
      <div className="mx-auto max-w-5xl space-y-6 p-6">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-base font-semibold">Benchmark</h2>
          <select value={run} onChange={e => setRun(e.target.value)} data-testid="bench-run" className="h-7 rounded-md border border-line bg-raised px-2 text-xs">
            {list.runs.map(r => <option key={r.run} value={r.run}>{r.run}</option>)}
          </select>
          {m && (
            <>
              {m.headline
                ? <Chip tone="green" title="Test split, with human labels">headline result</Chip>
                : <Chip tone="amber" title="Not a headline: see the notes below">not a headline result</Chip>}
              <Chip tone={m.meta.split === 'test' ? 'amber' : 'zinc'}>{m.meta.split} split</Chip>
              {m.meta.mode === 'replay' && <Chip tone="amber">REPLAY: answers from the cache</Chip>}
              <span className="text-[11px] text-muted">{m.n_mutated} injected + {m.n_clean} clean cases · seed {m.meta.seed} · code {m.meta.code?.commit ?? '?'}</span>
            </>
          )}
        </div>
        {error && <p className="text-xs text-red-300">{error}</p>}
        {!m ? <p className="text-sm text-muted">Loading…</p> : (
          <>
            <ul className="space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200" data-testid="caveats">
              {m.caveats.map(c => <li key={c}>• {c}</li>)}
            </ul>

            <Section title="Against human labels" testid="human"
              note="Precision and recall are per screen: Fixel flags a screen when it confirms at least one finding. Screens labelled unsure are left out. Each person's label was given blind.">
              {!h ? (
                <div className="rounded-lg border border-dashed border-line p-4 text-xs text-muted" data-testid="no-labels">
                  No human labels for this run yet. Open the <b>Label</b> tab to label {toLabel || 'the'} screens; this section fills in from them.
                </div>
              ) : (
                <>
                  <p className="text-[11px] text-muted">{m.labels.n} labelled: {m.labels.visible_defect} visible defect, {m.labels.no_visible_defect} none, {m.labels.unsure} unsure.</p>
                  <Table testid="human-table" head={['Detection stack', 'Precision', 'Recall', 'False positives on clean pages']}
                    rows={levels.map(lv => [LEVEL[lv], <RateCell r={(h as Record<string, HumanLevel>)[lv]?.precision} />,
                      <RateCell r={(h as Record<string, HumanLevel>)[lv]?.recall} />,
                      <RateCell r={(h as Record<string, HumanLevel>)[lv]?.clean_false_positive_rate} tone="rose" />])} />
                </>
              )}
            </Section>

            <Section title="By construction" testid="construction"
              note="Cases with a known answer that needs no geometry. A ghost banner paints over a button but hit testing sees through it, so it measures a known gap: Fixel starts occlusion from hit testing and SAM only confirms.">
              <Table head={['Case', ...levels.map(l => LEVEL[l])]}
                rows={[...OPS_BANNER, ...CONTROLS].map(([op, text]) => [text, ...levels.map(lv => <RateCell r={m.construction[lv]?.[op]} tone="emerald" />)])} />
            </Section>

            <Section title="Agreement with the injected defect" testid="agreement"
              note="Not detection accuracy. It asks whether Fixel reported the kind of defect that was injected, and is a regression signal for tuning on the development split. Humans decide what is really visible.">
              <Table head={['Operator', ...levels.map(l => LEVEL[l])]}
                rows={[...Object.keys(m.injected_agreement[levels[levels.length - 1]] ?? {}).filter(k => !k.startsWith('_')).map(op =>
                  [op.replace(/_/g, ' '), ...levels.map(lv => <RateCell r={m.injected_agreement[lv]?.[op]} />)]),
                  ['all operators', ...levels.map(lv => <RateCell r={m.injected_agreement[lv]?._all} />)],
                  ['…and named the element that was changed', ...levels.map(lv => <RateCell r={m.localization[lv]} />)]]} />
            </Section>

            <Section title="Cost and time" testid="cost">
              <p className="text-xs text-zinc-300">
                {m.cost.usd != null ? `$${m.cost.usd.toFixed(3)}` : 'n/a'} for {m.n_cases} cases ({m.cost.usd_per_case ?? 'n/a'} per case), {m.cost.seconds_per_case ?? 'n/a'} s per case.
                Model calls: {m.cost.model_calls ? `${m.cost.model_calls.live} live, ${m.cost.model_calls.cached} cached` : 'n/a'}.
              </p>
            </Section>
            <p className="pb-6 text-[11px] text-muted">
              Not measured yet: verified-fix rate, revert-equivalence, linter blocks and regressions caught (the fix benchmark), the triage and fixer model ablations, and synthetic and Storybook corpora.
              <button className="ml-2 underline" onClick={() => useStore.getState().set({ view: 'label' })}>Label screens</button>
            </p>
          </>
        )}
      </div>
    </div>
  )
}

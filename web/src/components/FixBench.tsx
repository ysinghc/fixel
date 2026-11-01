import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { FixArm, FixBenchList, FixBenchMetrics, Rate, RollJob } from '../types'
import { Button, Card, Chip } from './ui'

function R({ r }: { r: Rate | null | undefined }) {
  if (!r) return <span className="text-muted">–</span>
  return <span title={`${r.k} of ${r.n} · 95% interval ${Math.round(r.lo * 100)}–${Math.round(r.hi * 100)}%`}><span className="tabular-nums text-zinc-100">{Math.round(r.p * 100)}%</span> <span className="text-[11px] tabular-nums text-muted">{r.k}/{r.n}</span></span>
}

const ARM_NAME: Record<string, string> = { lint_on: 'Linter on (the product)', lint_off: 'Linter off (ablation)' }

function Row({ label, children, help }: { label: string; children: React.ReactNode; help?: string }) {
  return (
    <tr className="border-t border-line">
      <td className="px-4 py-2.5 text-zinc-300" title={help}>{label}</td>
      <td className="px-4 py-2.5 text-right">{children}</td>
    </tr>
  )
}

function ArmCard({ name, a }: { name: string; a: FixArm }) {
  return (
    <div className="min-w-0 flex-1 overflow-hidden rounded-xl border border-line" data-testid={`fixarm-${name}`}>
      <div className="bg-raised px-4 py-2.5 text-[13px] font-medium">{ARM_NAME[name] ?? name} <span className="text-[11px] font-normal text-muted">{a.n} attempts</span></div>
      <table className="w-full text-[13px]"><tbody>
        <Row label="Verified-fix rate" help="The model-free verifier passed: target gone everywhere, nothing new, no drift, build ok"><R r={a.verified} /></Row>
        <Row label="Revert-equivalence" help="Verified fixes whose pages render pixel-identical to the unmutated original at every state"><R r={a.revert_equivalent} /></Row>
        <Row label="Linter blocks" help="Edits the linter reverted"><span className="tabular-nums">{a.linter_blocks}</span> <span className="text-[11px] text-muted">in {a.cases_with_a_block} cases</span></Row>
        <Row label="Removed the target, failed the matrix" help="Patches that fixed the target but broke something else, caught by the verifier"><span className="tabular-nums">{a.removed_target_but_failed_the_matrix}</span></Row>
        {name === 'lint_off' && <Row label="Passed by hiding the symptom" help="Verified patches the linter would have blocked"><R r={a.patches_that_pass_by_hiding_the_symptom} /></Row>}
        <Row label="Failed or gave up"><span className="tabular-nums">{a.gave_up_or_failed}</span></Row>
        <Row label="Cost per attempt" help="Only the first arm is measured: the second replays its cached turns until they diverge">{a.usd_per_fix_attempt != null ? `$${a.usd_per_fix_attempt.toFixed(3)}` : 'not measured'}</Row>
        <Row label="Time per attempt"><span className="tabular-nums">{a.seconds_per_fix_attempt ?? '–'} s</span> <span className="text-[11px] text-muted">{a.turns_mean ?? '–'} turns</span></Row>
      </tbody></table>
    </div>
  )
}

/** Measured fix-benchmark results, from the injected-source runs. Nothing here is a headline: the cases are injected. */
export function FixBenchResults() {
  const [list, setList] = useState<FixBenchList | null>(null)
  const [run, setRun] = useState('')
  const [m, setM] = useState<FixBenchMetrics | null>(null)
  useEffect(() => { api.fixBench().then(l => { setList(l); if (l.runs[0]) setRun(l.runs[0].run) }).catch(() => setList({ available: false, runs: [], reason: 'the API is not reachable' })) }, [])
  useEffect(() => {
    if (!run) return
    let current = true
    setM(null)
    api.fixBenchMetrics(run).then(x => { if (current) setM(x) }).catch(() => {})
    return () => { current = false }
  }, [run])

  if (!list) return <div className="skeleton h-40 rounded-xl" />
  if (!list.available) {
    return <p className="text-xs text-muted" data-testid="fixbench-none">{list.reason}. <code className="rounded bg-black/40 px-1 py-0.5 font-mono">fixel bench fix --split dev</code> measures verified-fix rate, revert-equivalence, linter blocks and regressions caught.</p>
  }
  return (
    <div className="space-y-4" data-testid="fixbench">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="amber">not a headline result</Chip>
        <span className="text-xs text-zinc-300">Every case is an injected source defect. {m?.split !== 'test' ? 'Development split: a tuning signal, not a result.' : ''}</span>
        {m?.mode === 'replay' && <Chip tone="amber">REPLAY</Chip>}
        {list.runs.length > 1 && (
          <select value={run} onChange={e => setRun(e.target.value)} className="ml-auto h-8 rounded-lg border border-line bg-raised px-2 text-xs" data-testid="fixbench-run">
            {list.runs.map(r => <option key={r.run} value={r.run}>{r.run}</option>)}
          </select>
        )}
      </div>
      {!m ? <div className="skeleton h-48 rounded-xl" /> : (
        <>
          <p className="text-xs text-muted">
            {m.n_cases} defects injected into the source of real apps{m.requested ? ` (${m.requested} requested; ${m.no_applicable_element ?? 0} draws found no element the operator could edit)` : ''}; the model-free scan found <R r={m.detection_of_injected_source_defects} /> of them, and only those were handed to {m.model}.
            Spend ${m.usd.toFixed(2)}. The linter-off arm reuses the cached turns of the linter-on arm until the two diverge.
          </p>
          <div className="flex flex-col gap-3 md:flex-row">{Object.entries(m.arms).map(([k, a]) => <ArmCard key={k} name={k} a={a} />)}</div>
          {m.recorded_blocked_attempt && (
            <Card title="A recorded blocked attempt" testid="blocked-attempt">
              <p className="mb-2 text-xs text-amber-200">Recorded from {m.recorded_blocked_attempt.case}, not live: {m.recorded_blocked_attempt.lint.join('; ')}</p>
              <pre className="max-h-48 overflow-auto rounded-lg bg-black/40 p-2 text-[11px] text-zinc-300">{m.recorded_blocked_attempt.diff}</pre>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

const STEP_TONE: Record<string, string> = { note: 'text-zinc-300', tool: 'text-sky-300', blocked: 'text-red-300', verify: 'text-emerald-300' }

/** Draw a seed, inject a defect into a real app's source, find it, fix it. The seed is shown so anyone can roll the same case. */
export function RollCase() {
  const [job, setJob] = useState<RollJob | null>(null)
  const [seedText, setSeedText] = useState('')
  const [error, setError] = useState('')
  const timer = useRef<number | undefined>(undefined)
  const busy = job?.status === 'queued' || job?.status === 'running'

  useEffect(() => {
    if (!job || !busy) return
    timer.current = window.setTimeout(() => api.rollStatus(job.id).then(setJob).catch(e => setError(String(e.message))), 1200)
    return () => window.clearTimeout(timer.current)
  }, [job, busy])

  const start = () => {
    setError('')
    const n = Number(seedText)
    api.roll(Number.isInteger(n) && n > 0 ? n : undefined).then(setJob).catch(e => setError(String(e.message)))
  }
  const res = job?.result
  const arm = res?.arms?.lint_on
  return (
    <Card title="Roll a case" testid="roll" aside={job && <Chip tone="amber">injected defect, seed {job.seed}</Chip>}>
      <p className="mb-3 text-xs text-muted">Draws a random seed, injects a defect into the source of a development-split app, scans it with the model-free checks, and repairs it with the linter on. The same seed always draws the same case.</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button kind="primary" size="md" onClick={start} disabled={busy} data-testid="roll-go">{busy ? 'Rolling…' : 'Roll a case'}</Button>
        <input value={seedText} onChange={e => setSeedText(e.target.value)} placeholder="seed (optional)" inputMode="numeric" aria-label="seed"
          className="h-9 w-36 rounded-lg border border-line bg-raised px-2 text-xs" data-testid="roll-seed" />
        {job?.mode === 'replay' && <Chip tone="amber">REPLAY: only recorded seeds work</Chip>}
      </div>
      {error && <p className="mt-3 text-xs text-red-300" data-testid="roll-error">{error}</p>}
      {job && (
        <div className="mt-4 space-y-3" data-testid="roll-log">
          <ol className="space-y-1 font-mono text-[11px]">
            {job.log.map((l, i) => <li key={i} className={STEP_TONE[l.t]}>{l.t === 'note' ? l.text : `  ${l.t === 'blocked' ? '✗' : '→'} ${l.text}`}</li>)}
            {busy && <li className="pulse text-muted">working…</li>}
          </ol>
          {job.status === 'error' && <p className="text-xs text-red-300" data-testid="roll-failed">{job.error}</p>}
          {res?.error && <p className="text-xs text-amber-200">{res.error}</p>}
          {res && !res.error && (
            <div className="rounded-lg border border-line bg-black/20 p-3 text-xs" data-testid="roll-result">
              {!res.detected ? <p>The injected defect at <code className="font-mono">{res.loc}</code> was not found by the scan, so nothing was handed to the fixer. That is reported, not hidden.</p> : arm && (
                <>
                  {!!res.undetected_draws_skipped && <p className="mb-2 text-muted">{res.undetected_draws_skipped} earlier draw{res.undetected_draws_skipped > 1 ? 's' : ''} for this seed injected a defect the scan could not see and {res.undetected_draws_skipped > 1 ? 'were' : 'was'} redrawn.</p>}
                  <p className="mb-2 flex flex-wrap items-center gap-2">
                    {arm.status === 'verified' ? <Chip tone="green">verified by the model-free verifier</Chip> : <Chip tone="red">not verified: {arm.status}</Chip>}
                    {arm.equivalent && <Chip tone={arm.equivalent.identical ? 'green' : 'zinc'}>{arm.equivalent.identical ? 'renders identical to the original' : `${arm.equivalent.states_identical}/${arm.equivalent.states} screens identical to the original`}</Chip>}
                    {arm.blocked > 0 && <Chip tone="red">linter blocked {arm.blocked} edit{arm.blocked > 1 ? 's' : ''}</Chip>}
                    <span className="text-muted">{arm.seconds}s · ${(res.usd ?? 0).toFixed(3)}</span>
                  </p>
                  <pre className="max-h-48 overflow-auto rounded bg-black/40 p-2 text-[11px] text-zinc-300">{arm.diff || '(no edits)'}</pre>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

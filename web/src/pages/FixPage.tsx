import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { TYPE_LABEL, locLabel } from '../fmt'
import { paths } from '../paths'
import { useStore } from '../store'
import type { Fix } from '../types'
import { BeforeAfter, CHECK_LABEL, CheckList, Diffs, FIX_STATUS, Grid, Timeline, modelName } from '../components/fix'
import { Button, Card, Chip, Progress, Tabs } from '../components/ui'
import { CHECKS } from '../types'

const PHASES = ['Reproduce on the current code', 'Edit the code', 'Verify on every screen', 'Result']
const phaseOf = (s: Fix['status']) => (s === 'queued' || s === 'baseline' ? 0 : s === 'working' ? 1 : s === 'verifying' ? 2 : 3)

/** Four connected phases: where the fix is now, and how far it has to go (uniform connectedness, goal gradient). */
function Stepper({ fix, total }: { fix: Fix; total: number }) {
  const cur = phaseOf(fix.status)
  const edits = fix.patches.length, blocked = fix.patches.filter(p => p.lint.length).length
  const checked = Object.keys(fix.cells).length
  const detail = [
    fix.status === 'queued' ? 'waiting for another fix to finish' : `${fix.baseline.done} of ${fix.baseline.total} screens`,
    edits ? `${edits} edit${edits === 1 ? '' : 's'}${blocked ? `, ${blocked} blocked by the linter` : ''}` : 'reading the code',
    `${checked} of ${total} screens`,
    FIX_STATUS[fix.status].text,
  ]
  return (
    <ol className="flex items-start" data-testid="stepper">
      {PHASES.map((p, i) => {
        const state = i < cur || (i === 3 && cur === 3) ? 'done' : i === cur ? 'now' : 'todo'
        const bad = i === 3 && cur === 3 && fix.status !== 'verified'
        return (
          <li key={p} className="flex flex-1 items-start" data-testid="step" data-state={state}>
            <div className="flex flex-col items-center">
              <span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${bad ? 'bg-red-500 text-white' : state === 'done' ? 'bg-emerald-500 text-black' : state === 'now' ? 'pulse bg-sky-500 text-white' : 'border border-line bg-raised text-muted'}`}>
                {bad ? '✗' : state === 'done' ? '✓' : i + 1}
              </span>
            </div>
            <div className="ml-2 min-w-0 flex-1 pr-2">
              <div className={`text-xs font-medium ${state === 'todo' ? 'text-muted' : 'text-zinc-100'}`}>{p}</div>
              <div className="text-[11px] text-muted">{state === 'todo' ? '' : detail[i]}</div>
              {i === 0 && state === 'now' && fix.baseline.total > 0 && <div className="mt-1 w-32"><Progress value={fix.baseline.done} total={fix.baseline.total} /></div>}
            </div>
            {i < PHASES.length - 1 && <span className={`mt-3.5 h-0.5 w-8 flex-none rounded ${i < cur ? 'bg-emerald-500/70' : 'bg-line'}`} />}
          </li>
        )
      })}
    </ol>
  )
}

/** The end of the story gets the clearest moment: verified with a download, or plainly why not (peak-end rule). */
function Verdict({ fix, screens }: { fix: Fix; screens: number }) {
  const r = fix.result
  if (fix.status === 'error') {
    return <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200" data-testid="fix-error">The fix could not run: {fix.error}</div>
  }
  if (!r) return null
  if (r.status === 'verified') {
    return (
      <div className="flex flex-wrap items-center gap-4 rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-5" data-testid="verdict" data-ok="true">
        <span className="grid h-11 w-11 flex-none place-items-center rounded-full bg-emerald-500 text-xl font-bold text-black">✓</span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-emerald-100">Verified: the bug is gone on all {screens} screens</div>
          <p className="mt-0.5 text-xs text-emerald-200/80">Nothing else moved, the linter accepted the patch and the build passes. {r.summary}</p>
        </div>
        <a href={api.patchUrl(fix.id)} download data-testid="export" className="inline-flex h-11 items-center rounded-lg bg-emerald-500 px-5 text-sm font-semibold text-black hover:bg-emerald-400">Download .patch</a>
      </div>
    )
  }
  const failed = CHECKS.filter(c => fix.checks[c] === false)
  return (
    <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-5" data-testid="verdict" data-ok="false">
      <div className="flex flex-wrap items-center gap-4">
        <span className="grid h-11 w-11 flex-none place-items-center rounded-full bg-red-500 text-xl font-bold text-white">✗</span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-red-100" data-testid="not-verified">Not verified: nothing is shown as fixed</div>
          <p className="mt-0.5 text-xs text-red-200/80">
            {failed.length ? `Failed: ${failed.map(c => CHECK_LABEL[c].toLowerCase()).join('; ')}.` : FIX_STATUS[fix.status].text}
            {' '}Your code was not changed: fixes run in an isolated copy.
          </p>
        </div>
        <Button disabled data-testid="export" size="lg" title="Only a patch the verifier passed can be downloaded">Download .patch</Button>
      </div>
    </div>
  )
}

export function FixPage() {
  const { run: runParam = '', fix: fixId = '' } = useParams()
  const fix = useStore(s => s.fixes[fixId])
  const finding = useStore(s => (fix ? s.findings[fix.key] : undefined))
  const run = useStore(s => s.run)
  const states = useStore(s => s.states)
  const [tab, setTab] = useState<'proof' | 'changes' | 'log' | null>(null)
  useEffect(() => setTab(null), [fixId])

  const r = fix?.result
  const stateKeys = useMemo(() => {
    if (r?.states?.length) return r.states
    if (!run) return []
    const route = states[finding?.candidates[0]?.state_key ?? '']?.route ?? run.routes[0]
    return run.widths.flatMap(w => run.themes.flatMap(t => run.text_stress.map(s => `${route}|${w}|${t}|${s}|0`)))
  }, [r, run, states, finding])
  const showKey = useMemo(() => {
    const cs = [...(finding?.candidates ?? [])].sort((a, b) => (states[a.state_key]?.width ?? 1e9) - (states[b.state_key]?.width ?? 1e9))
    return cs[0]?.state_key
  }, [finding, states])

  if (!fix) {
    return (
      <div className="mx-auto max-w-5xl p-4 md:p-8" data-testid="fix-loading">
        <Link to={paths.run(runParam)} className="text-xs text-muted hover:text-zinc-200">← All findings</Link>
        <h1 className="mt-1 text-xl font-semibold">Starting the fix…</h1>
        <div className="skeleton mt-6 h-40 rounded-xl" />
      </div>
    )
  }

  const finished = !!r || fix.status === 'error'
  const active = tab ?? (finished ? 'proof' : 'log')
  const blocked = fix.patches.filter(p => p.lint.length).length

  return (
    <div className="mx-auto max-w-6xl p-4 md:p-8" data-testid="fix-page" data-fix={fix.id}>
      <header className="mb-5 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <Link to={paths.finding(runParam, fix.key)} className="text-xs text-muted hover:text-zinc-200" data-testid="back">← Back to the finding</Link>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">Fix: {finding ? TYPE_LABEL[finding.type] ?? finding.type : fix.key}</h1>
            {finding?.locs[0] && <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[12px] text-sky-300">{locLabel(finding.locs[0])}</code>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Chip tone={FIX_STATUS[fix.status].tone} className="font-semibold"><span data-testid="fix-status">{FIX_STATUS[fix.status].text}</span></Chip>
          <Chip tone="violet" title="The model that wrote the patch"><span data-testid="fix-model">{modelName(fix.model)}</span></Chip>
          {fix.fallback && <Chip tone="amber" title={`${fix.fallback.from} was unavailable`}><span data-testid="fallback">fallback from Wonder</span></Chip>}
          {r && <span className="text-[11px] text-muted">{r.turns} turns · {r.tokens.toLocaleString()} tokens</span>}
        </div>
      </header>

      <Card className="mb-5"><Stepper fix={fix} total={stateKeys.length} /></Card>
      {finished && <div className="mb-5"><Verdict fix={fix} screens={stateKeys.length} /></div>}

      <Tabs value={active} onChange={setTab} testid="fix-tabs" items={[
        { value: 'proof', label: 'Proof', testid: 'tab-proof', title: 'Before and after, every screen re-rendered, and the five checks' },
        { value: 'changes', label: 'Code changes', count: fix.patches.length + (r?.diff ? 1 : 0), testid: 'tab-changes', title: 'Each edit, with the linter blocks' },
        { value: 'log', label: 'Agent log', count: fix.timeline.length, testid: 'tab-log', title: 'Every step the model took' },
      ]} />

      {active === 'proof' && (
        <div className="grid gap-5 lg:grid-cols-[1fr_1fr]" data-testid="proof">
          <Card title="Before and after" aside={<span className="text-[11px] text-muted">drag the slider</span>}>
            <BeforeAfter fix={fix} before={showKey ? r?.before_shots?.[showKey] : undefined} after={showKey ? r?.verification?.shots?.[showKey] : undefined} />
          </Card>
          <div className="space-y-5">
            <Card title="Every screen, re-rendered" aside={<span className="text-[11px] text-muted">green: bug gone</span>}>
              <Grid fix={fix} states={stateKeys} />
            </Card>
            <Card title="Checks"><CheckList fix={fix} /></Card>
            {r?.verification && r.verification.notes.length > 0 && (
              <pre className="max-h-40 overflow-auto rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-[11px] text-red-200" data-testid="notes">{r.verification.notes.join('\n')}</pre>
            )}
            {r?.verification && (r.verification.new_findings.length > 0 || r.verification.drifted.length > 0) && (
              <div className="text-xs text-amber-300" data-testid="regressions">
                {r.verification.new_findings.length > 0 && <div>New defects: {r.verification.new_findings.join(', ')}</div>}
                {r.verification.drifted.length > 0 && <div>Moved or resized: {r.verification.drifted.join(', ')}</div>}
              </div>
            )}
          </div>
        </div>
      )}
      {active === 'changes' && (
        <div>
          {blocked > 0 && <p className="mb-3 text-xs text-muted">{blocked} edit{blocked === 1 ? ' was' : 's were'} blocked by the linter for hiding the symptom instead of fixing it, and reverted.</p>}
          <Diffs fix={fix} />
        </div>
      )}
      {active === 'log' && <Timeline fix={fix} />}
    </div>
  )
}

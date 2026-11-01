import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { paths } from '../paths'
import { useStore } from '../store'
import { SplitChip } from '../components/RunBits'
import { Button, PageHeader } from '../components/ui'

function Step({ n, title, hint, children }: { n: number; title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-panel p-5">
      <div className="mb-4 flex items-start gap-3">
        <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-sky-500/20 text-xs font-bold text-sky-200">{n}</span>
        <div><h2 className="text-[14px] font-semibold">{title}</h2>{hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}</div>
      </div>
      {children}
    </section>
  )
}

function Choice({ on, onClick, title, text, aside, disabled, testid }: { on: boolean; onClick: () => void; title: ReactNode; text?: ReactNode; aside?: ReactNode; disabled?: boolean; testid?: string }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} data-testid={testid} data-on={on} role="radio" aria-checked={on}
      className={`flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${on ? 'border-sky-500/60 bg-sky-500/10' : 'border-line bg-raised hover:border-zinc-600'}`}>
      <span className={`mt-0.5 grid h-4 w-4 flex-none place-items-center rounded-full border-2 ${on ? 'border-sky-400' : 'border-zinc-600'}`}>{on && <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />}</span>
      <span className="min-w-0 flex-1"><span className="flex items-center gap-2 text-[13px] font-medium">{title}{aside}</span>{text && <span className="mt-0.5 block text-xs text-muted">{text}</span>}</span>
    </button>
  )
}

/** Three steps and one button. The matrix of widths and themes comes from the app's config: shown, not asked (Tesler's law). */
export function ScanSetup() {
  const targets = useStore(s => s.targets)
  const config = useStore(s => s.appConfig)
  const navigate = useNavigate()
  const [pick, setPick] = useState('')
  const [route, setRoute] = useState('')
  const [models, setModels] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (targets.length && !pick) {
      const t = targets.find(x => x.name === 'demo-shop') ?? targets.find(x => x.split === 'demo') ?? targets[0]
      setPick(t.config); setRoute(t.routes[0])
    }
  }, [targets, pick])
  useEffect(() => { if (config) setModels(config.models_available) }, [config])

  const target = targets.find(t => t.config === pick)
  const routes = target ? (route === '*' ? target.routes : [route]) : []
  const n = target ? routes.length * target.widths.length * target.themes.length * target.text_stress.length : 0
  const ordered = useMemo(() => [...targets].sort((a, b) => Number(b.split === 'demo') - Number(a.split === 'demo')), [targets])

  const start = async () => {
    setError(''); setBusy(true)
    try {
      const { run_id } = await api.scan({ config: pick, routes: route === '*' ? undefined : [route], models })
      navigate(paths.run(run_id))
    } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  return (
    <div className="mx-auto max-w-5xl p-4 md:p-8" data-testid="scan-setup">
      <PageHeader title="New scan" subtitle="Pick an app and its pages. Fixel renders each one at every width and theme, then checks what is actually painted." />
      <div className="grid items-start gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          <Step n={1} title="Choose an app" hint="The apps configured in targets/. The demo app has three planted bugs.">
            <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" data-testid="target-list">
              {ordered.map(t => (
                <Choice key={t.config} on={t.config === pick} onClick={() => { setPick(t.config); setRoute(t.routes[0]) }} testid={`target-${t.name}`}
                  title={t.name} aside={<SplitChip split={t.split} />} text={`${t.routes.length} page${t.routes.length === 1 ? '' : 's'}`} />
              ))}
              {!targets.length && <p className="text-xs text-muted">No apps configured. Add a YAML file under targets/.</p>}
            </div>
          </Step>

          {target && (
            <Step n={2} title="Choose pages" hint="Start with one page; scanning all of them takes longer.">
              <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" data-testid="route-list">
                {target.routes.map(r => <Choice key={r} on={route === r} onClick={() => setRoute(r)} title={<code className="font-mono text-[12px]">{r}</code>} testid={`route-${r}`} />)}
                {target.routes.length > 1 && <Choice on={route === '*'} onClick={() => setRoute('*')} title={`All ${target.routes.length} pages`} testid="route-all" />}
              </div>
            </Step>
          )}

          <Step n={3} title="Choose the evidence" hint="Both decide findings by code. The models can only dismiss a finding, never invent one.">
            <div className="grid gap-2" role="radiogroup">
              <Choice on={models} onClick={() => setModels(true)} disabled={!config?.models_available} testid="evidence-full"
                title="Full check" text={config?.models_available ? 'Geometry, the pixel diff, SAM 3.1 on the pixels and a Spark 1.3 description of each finding. Uses model credit; cached answers are free.' : 'Needs an API key in .env (MODEL_API_KEY).'} />
              <Choice on={!models} onClick={() => setModels(false)} testid="evidence-quick"
                title="Quick check" text="Geometry and the pixel diff only. No model calls, no cost." />
            </div>
          </Step>
        </div>

        <aside className="sticky top-6 rounded-xl border border-line bg-panel p-5" data-testid="summary">
          <h2 className="text-[13px] font-semibold">Summary</h2>
          {target ? (
            <dl className="mt-3 space-y-2.5 text-xs">
              <div><dt className="text-muted">App</dt><dd className="mt-0.5 text-zinc-200">{target.name}</dd></div>
              <div><dt className="text-muted">Pages</dt><dd className="mt-0.5 font-mono text-zinc-200">{routes.join(', ')}</dd></div>
              <div><dt className="text-muted">Widths</dt><dd className="mt-1 flex flex-wrap gap-1">{target.widths.map(w => <span key={w} className="rounded bg-raised px-1.5 py-0.5 tabular-nums text-zinc-300">{w}</span>)}</dd></div>
              <div><dt className="text-muted">Themes and text</dt><dd className="mt-0.5 text-zinc-200">{target.themes.join(', ')} · {target.text_stress.map(x => (x === 'pseudo' ? 'long text' : 'normal text')).join(', ')}</dd></div>
            </dl>
          ) : <div className="skeleton mt-3 h-24 rounded-lg" />}
          <div className="mt-4 border-t border-line pt-4">
            <p className="mb-3 text-sm"><b className="tabular-nums" data-testid="state-count">{n}</b> screens to render</p>
            <Button kind="primary" size="lg" className="w-full" onClick={start} disabled={!target || busy} data-testid="scan-button">{busy ? 'Starting…' : 'Start scan'}</Button>
            {error && <p className="mt-2 text-xs text-red-300" data-testid="scan-error">{error}</p>}
          </div>
        </aside>
      </div>
    </div>
  )
}

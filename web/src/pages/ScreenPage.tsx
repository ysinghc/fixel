import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { TYPE_LABEL, widthRange } from '../fmt'
import { paths } from '../paths'
import { useStore } from '../store'
import { Viewer } from '../components/Viewer'

/** One rendered screen with every finding on it. */
export function ScreenPage() {
  const { run = '', state = '' } = useParams()
  const stateKey = useStore(s => s.stateKey)
  const exists = useStore(s => !!s.states[state])
  const findings = useStore(s => s.findings)
  const here = Object.values(findings).filter(f => f.candidates.some(c => c.state_key === stateKey))

  useEffect(() => {
    if (exists) useStore.getState().set({ findingKey: null })
    if (exists) useStore.getState().selectState(state)
  }, [state, exists])
  useEffect(() => () => useStore.getState().set({ stateKey: null }), [])

  return (
    <div className="flex h-full flex-col px-6 pb-4 pt-5" data-testid="screen-page">
      <header className="flex-none pb-4">
        <Link to={paths.screens(run)} className="text-xs text-muted hover:text-zinc-200" data-testid="back">← All screens</Link>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">One screen</h1>
      </header>
      <div className="flex min-h-0 flex-1 gap-5">
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-line bg-ink"><Viewer /></div>
        <aside className="w-[300px] flex-none overflow-y-auto">
          <h2 className="mb-2 text-[13px] font-semibold">Findings on this screen</h2>
          {here.length === 0 ? <p className="text-xs text-muted">None. Widths with findings are the ones with a red count on the Screens page.</p> : (
            <ul className="space-y-1.5">
              {here.map(f => (
                <li key={f.key}><Link to={paths.finding(run, f.key)} onMouseEnter={() => useStore.getState().set({ hoverKey: f.key })} onMouseLeave={() => useStore.getState().set({ hoverKey: null })}
                  className="flex items-center gap-2 rounded-lg border border-line bg-raised px-3 py-2 text-xs hover:border-zinc-500" data-testid="screen-finding">
                  <span className="font-medium">{TYPE_LABEL[f.type] ?? f.type}</span><span className="ml-auto text-muted">{f.status === 'confirmed' ? widthRange(f.widths) : f.status.replace('_', ' ')}</span>
                </Link></li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  )
}

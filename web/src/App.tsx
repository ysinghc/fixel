import { useEffect, useState } from 'react'
import { api, type AppConfig, type Target } from './api'
import { BenchmarkView } from './components/BenchmarkView'
import { FindingsPanel } from './components/FindingsPanel'
import { FixDrawer } from './components/FixDrawer'
import { LabelView } from './components/LabelView'
import { Stage } from './components/Stage'
import { StateRail } from './components/StateRail'
import { TopBar } from './components/TopBar'
import { useRunEvents } from './hooks/useRunEvents'
import { sortedFindings, useStore } from './store'

/** j/k move between findings, f opens Fix, v is voice (not built), 1-4 toggle the overlay layers, Esc closes the drawer. */
function useKeyboard() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA' || e.metaKey || e.ctrlKey || e.altKey) return
      const s = useStore.getState()
      if (s.view !== 'scan') return
      if (e.key === 'j' || e.key === 'k') {
        const list = sortedFindings(s.findings, s.tab)
        if (!list.length) return
        const i = list.findIndex(f => f.key === s.findingKey)
        const next = list[Math.max(0, Math.min(list.length - 1, i + (e.key === 'j' ? 1 : -1)))]
        s.selectFinding(next.key)
      } else if (e.key === 'f') {
        const f = s.findingKey ? s.findings[s.findingKey] : undefined
        if (f && f.status === 'confirmed' && s.runId) void api.fix(s.runId, f.key).catch(() => {})
      } else if (e.key === 'Escape') s.set({ drawer: false })
      else if (['1', '2', '3', '4'].includes(e.key)) s.toggleLayer((['dom', 'sam', 'candidates', 'findings'] as const)[Number(e.key) - 1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [targets, setTargets] = useState<Target[]>([])
  const [apiError, setApiError] = useState('')
  const runId = useStore(s => s.runId)
  const view = useStore(s => s.view)
  const drawer = useStore(s => s.drawer)
  const fixId = useStore(s => s.fixId)

  useEffect(() => {
    api.config().then(c => { setConfig(c); useStore.getState().set({ appConfig: c }) }).catch(e => setApiError(String(e.message)))
    api.targets().then(t => { setTargets(t); useStore.getState().set({ targets: t }) }).catch(() => {})
    // reopen the most recent run, so a reload (or a judge's second tab) rebuilds the same screen from its event log
    api.runs().then(rs => { const r = rs.find(x => x.kind === 'scan'); if (r && !useStore.getState().runId) useStore.getState().reset(r.id) }).catch(() => {})
  }, [])
  useRunEvents(runId)
  useKeyboard()

  return (
    <div className="flex h-full flex-col" data-testid="app">
      <TopBar config={config} targets={targets} />
      {apiError && <div className="bg-red-500/15 px-4 py-2 text-xs text-red-200">Cannot reach the Fixel API: {apiError}. Start it with <code>fixel serve</code>.</div>}
      {config?.mode === 'replay' && (
        <div className="bg-amber-400 px-4 py-1 text-center text-xs font-semibold text-black" data-testid="replay-banner">
          REPLAY MODE — model responses come from the cache; nothing is being called or spent.
        </div>
      )}
      {view === 'bench' ? <BenchmarkView /> : view === 'label' ? <LabelView /> : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1">
            <StateRail />
            <Stage />
            <FindingsPanel />
          </div>
          {drawer && fixId && <FixDrawer />}
        </div>
      )}
    </div>
  )
}

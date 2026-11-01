import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../api'
import { paths } from '../paths'
import { useStore } from '../store'
import { Icon } from '../components/ui'

// Five destinations, in the order of the job: start, scan, review, label, read the results (Hick's law, serial position)
const NAV = [
  { to: paths.home, label: 'Home', icon: 'home', end: true, testid: 'nav-home' },
  { to: paths.scan, label: 'New scan', icon: 'scan', end: true, testid: 'nav-scan' },
  { to: paths.runs, label: 'Results', icon: 'results', end: false, testid: 'nav-runs' },
  { to: paths.label, label: 'Label', icon: 'label', end: true, testid: 'nav-label' },
  { to: paths.benchmark, label: 'Benchmark', icon: 'chart', end: true, testid: 'nav-benchmark' },
]

/** Loads what every page may need once: the server's mode and the configured targets. */
function useAppData(): string {
  const [error, setError] = useState('')
  useEffect(() => {
    api.config().then(c => useStore.getState().set({ appConfig: c })).catch(e => setError(String(e.message)))
    api.targets().then(t => useStore.getState().set({ targets: t })).catch(() => {})
  }, [])
  return error
}

export function Shell() {
  const error = useAppData()
  const config = useStore(s => s.appConfig)
  const replay = config?.mode === 'replay'
  return (
    <div className="flex h-full flex-col md:flex-row" data-testid="app">
      <nav className="flex flex-none flex-col border-b border-line bg-panel md:w-52 md:border-b-0 md:border-r" aria-label="Main">
        <div className="flex items-center gap-2 px-4 pb-2 pt-3 md:pb-4 md:pt-5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-sky-500 text-sm font-black text-white">F</span>
          <div>
            <div className="text-sm font-semibold leading-4">Fixel</div>
            <div className="text-[11px] text-muted">layout bug finder</div>
          </div>
        </div>
        <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-0.5 md:overflow-visible md:pb-0">
          {NAV.map(n => (
            <li key={n.to} className="flex-none">
              <NavLink to={n.to} end={n.end} data-testid={n.testid}
                className={({ isActive }) => `flex items-center gap-2 whitespace-nowrap rounded-lg px-2.5 py-1.5 md:gap-2.5 md:px-3 md:py-2 text-[13px] font-medium transition-colors ${isActive ? 'bg-sky-500/15 text-sky-100' : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-100'}`}>
                <Icon name={n.icon} />{n.label}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="mt-auto hidden space-y-2 border-t border-line p-4 text-[11px] text-muted md:block">
          {config && (
            <div className="flex items-center gap-2" data-testid="mode" title={replay ? 'Model answers come from the cache; nothing is spent' : config.mode === 'record' ? 'Live model calls, cached for replay' : 'Always calling the models'}>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${replay ? 'bg-amber-400 text-black' : 'bg-emerald-500/20 text-emerald-300'}`}>{replay ? 'REPLAY' : 'LIVE'}</span>
              <span>{replay ? 'answers from cache' : 'models called live'}</span>
            </div>
          )}
          {config && <div>{config.models_available ? 'SAM and Spark available' : 'No API key: geometry and pixels only'}</div>}
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        {replay && (
          <div className="flex-none bg-amber-400 px-4 py-1 text-center text-xs font-semibold text-black" data-testid="replay-banner">
            REPLAY MODE: model responses come from the cache; nothing is being called or spent.
          </div>
        )}
        {error && <div className="flex-none bg-red-500/15 px-4 py-2 text-xs text-red-200" data-testid="api-error">Cannot reach the Fixel API: {error}. Start it with <code>fixel serve</code>.</div>}
        <main className="min-h-0 flex-1 overflow-y-auto" data-testid="main"><Outlet /></main>
      </div>
    </div>
  )
}

import { api } from '../api'
import { stateKeyFor, useStore } from '../store'
import { Segmented } from './ui'

export function StateRail() {
  const run = useStore(s => s.run)
  const states = useStore(s => s.states)
  const findings = useStore(s => s.findings)
  const route = useStore(s => s.route)
  const theme = useStore(s => s.theme)
  const stress = useStore(s => s.stress)
  const stateKey = useStore(s => s.stateKey)
  const set = useStore(s => s.set)
  const selectState = useStore(s => s.selectState)

  if (!run) {
    return <aside className="w-60 flex-none border-r border-line bg-panel p-3 text-xs text-muted">The width filmstrip appears here once a scan starts.</aside>
  }

  const routes = run.routes
  const activeRoute = route && routes.includes(route) ? route : routes[0]
  const widths = [...run.widths].sort((a, b) => a - b)
  const perState: Record<string, number> = {}
  for (const f of Object.values(findings)) {
    if (f.status !== 'confirmed') continue
    for (const sk of new Set(f.candidates.map(c => c.state_key))) perState[sk] = (perState[sk] ?? 0) + 1
  }

  const go = (patch: { route?: string; theme?: string; stress?: string }) => {
    const r = patch.route ?? activeRoute, t = patch.theme ?? theme, s = patch.stress ?? stress
    set({ route: r, theme: t, stress: s })
    const cur = states[stateKey ?? '']
    const key = stateKeyFor(states, r, cur?.width ?? widths[0], t, s)
      ?? Object.values(states).find(x => x.route === r && x.theme === t && x.text_stress === s)?.key
    if (key) selectState(key)
  }

  return (
    <aside className="flex w-60 flex-none flex-col border-r border-line bg-panel" data-testid="rail">
      <div className="space-y-2 border-b border-line p-3">
        {routes.length > 1 && (
          <select value={activeRoute} onChange={e => go({ route: e.target.value })}
            className="h-7 w-full rounded-md border border-line bg-raised px-2 text-xs">
            {routes.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        )}
        <Segmented label="theme" value={theme} onChange={v => go({ theme: v })}
          options={run.themes.map(t => ({ value: t, label: t }))} />
        <Segmented label="text" value={stress} onChange={v => go({ stress: v })}
          options={run.text_stress.map(t => ({ value: t, label: t === 'pseudo' ? 'pseudo-loc' : t }))} />
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        {widths.map(w => {
          const key = stateKeyFor(states, activeRoute, w, theme, stress)
          const st = key ? states[key] : undefined
          const n = key ? perState[key] ?? 0 : 0
          const selected = key !== null && key === stateKey
          return (
            <button key={w} data-testid={`width-${w}`} disabled={!st || st.status === 'running'}
              onClick={() => key && selectState(key)}
              className={`flex w-full items-center gap-3 rounded-lg border p-2 text-left transition-colors ${selected ? 'border-sky-500/60 bg-sky-500/10' : 'border-transparent hover:bg-white/5'} disabled:cursor-default`}>
              <div className="relative h-[72px] w-14 flex-none overflow-hidden rounded border border-line bg-black/40">
                {st && st.status !== 'running' && st.tiles[0]
                  ? <img src={api.artifact(st.tiles[0].sha)} alt="" className="h-full w-full object-cover object-top" />
                  : <div className={st ? 'skeleton h-full w-full' : 'h-full w-full border border-dashed border-line'} />}
                {n > 0 && (
                  <span className="absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white"
                    data-testid={`width-count-${w}`}>{n}</span>
                )}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium tabular-nums">{w} px</div>
                <div className="text-[11px] text-muted">
                  {!st ? 'queued' : st.status === 'running' ? 'rendering…' : n ? `${n} finding${n > 1 ? 's' : ''}` : 'clean'}
                </div>
              </div>
            </button>
          )
        })}
      </div>

      <div className="border-t border-line p-3 text-[11px] text-muted">
        <div className="mb-1 uppercase tracking-wide">Explored states</div>
        <div className="text-zinc-500">The interaction explorer (menus, modals, forms) is not built yet.</div>
      </div>
    </aside>
  )
}

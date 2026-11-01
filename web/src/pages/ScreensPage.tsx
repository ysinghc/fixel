import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { paths } from '../paths'
import { useStore } from '../store'
import type { StateInfo } from '../types'
import { RunHeader } from '../components/RunHeader'

/** Every rendered screen as a grid: a row per theme and text setting, a column per width (proximity, common region). */
export function ScreensPage() {
  const runId = useStore(s => s.runId)
  const run = useStore(s => s.run)
  const states = useStore(s => s.states)
  const findings = useStore(s => s.findings)

  const perState = useMemo(() => {
    const m: Record<string, number> = {}
    for (const f of Object.values(findings)) {
      if (f.status !== 'confirmed') continue
      for (const k of new Set(f.candidates.map(c => c.state_key))) m[k] = (m[k] ?? 0) + 1
    }
    return m
  }, [findings])

  const all = Object.values(states)
  const routes = [...new Set(all.map(s => s.route))]
  const widths = run ? [...run.widths].sort((a, b) => a - b) : []
  const rows = run ? run.themes.flatMap(t => run.text_stress.map(x => ({ theme: t, stress: x }))) : []
  const find = (route: string, w: number, theme: string, stress: string): StateInfo | undefined =>
    all.find(s => s.route === route && s.width === w && s.theme === theme && s.text_stress === stress)

  return (
    <div className="mx-auto max-w-5xl p-4 md:p-8" data-testid="screens-page">
      <RunHeader />
      <p className="mb-4 text-xs text-muted">Every screen Fixel rendered. The red number is how many confirmed findings it shows. Open one to inspect it.</p>
      {routes.length === 0 && <div className="skeleton h-48 rounded-xl" />}
      {runId && routes.map(route => (
        <section key={route} className="mb-8">
          {routes.length > 1 && <h2 className="mb-2 font-mono text-[13px] text-zinc-300">{route}</h2>}
          <div className="overflow-x-auto">
            <table className="border-separate border-spacing-2">
              <thead><tr><th />{widths.map(w => <th key={w} className="text-[11px] font-medium tabular-nums text-muted">{w}px</th>)}</tr></thead>
              <tbody>
                {rows.map(r => (
                  <tr key={`${r.theme}-${r.stress}`}>
                    <th className="whitespace-nowrap pr-2 text-right text-[11px] font-medium text-muted">{r.theme}<br />{r.stress === 'pseudo' ? 'long text' : 'normal text'}</th>
                    {widths.map(w => {
                      const st = find(route, w, r.theme, r.stress)
                      const n = st ? perState[st.key] ?? 0 : 0
                      const ready = st && st.status !== 'running' && st.tiles[0]
                      return (
                        <td key={w} className="align-top">
                          {ready ? (
                            <Link to={paths.screen(runId, st.key)} data-testid={`screen-${w}-${r.theme}-${r.stress}`} data-count={n}
                              className="group relative block h-36 w-28 overflow-hidden rounded-lg border border-line bg-raised hover:border-sky-400">
                              <img src={api.artifact(st.tiles[0].sha)} alt="" className="h-full w-full object-cover object-top" loading="lazy" />
                              {n > 0 && <span className="absolute right-1 top-1 grid h-5 min-w-5 place-items-center rounded-full bg-red-500 px-1 text-[11px] font-bold text-white" data-testid="screen-count">{n}</span>}
                            </Link>
                          ) : <div className="skeleton h-36 w-28 rounded-lg" />}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  )
}

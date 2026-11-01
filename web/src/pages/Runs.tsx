import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, targetOf, type RunRow } from '../api'
import { paths } from '../paths'
import { ago, RunStatusChip } from '../components/RunBits'
import { ButtonLink, Empty, PageHeader } from '../components/ui'

/** Every scan, newest first; a whole row opens it. */
export function Runs() {
  const [runs, setRuns] = useState<RunRow[] | null>(null)
  const navigate = useNavigate()
  useEffect(() => { api.runs().then(rs => setRuns(rs.filter(r => r.kind === 'scan'))).catch(() => setRuns([])) }, [])

  return (
    <div className="mx-auto max-w-5xl p-8" data-testid="runs">
      <PageHeader title="Results" subtitle="Every scan, newest first. Open one to see its findings." actions={<ButtonLink to={paths.scan} kind="primary" size="md">New scan</ButtonLink>} />
      {runs === null ? <div className="skeleton h-40 rounded-xl" /> : runs.length === 0 ? (
        <Empty title="No scans yet" testid="runs-empty" action={<ButtonLink to={paths.scan} kind="primary" size="md">Start a scan</ButtonLink>}>Results appear here as soon as a scan starts.</Empty>
      ) : (
        <div className="overflow-hidden rounded-xl border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-raised text-[11px] uppercase tracking-wide text-muted">
              <tr><th className="px-4 py-2.5 font-medium">App</th><th className="px-4 py-2.5 font-medium">Status</th><th className="px-4 py-2.5 font-medium">Confirmed</th><th className="px-4 py-2.5 font-medium">Screens</th><th className="px-4 py-2.5 font-medium">Cost</th><th className="px-4 py-2.5 font-medium">Started</th></tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id} onClick={() => navigate(paths.run(r.id))} data-testid="run-row" className="cursor-pointer border-t border-line hover:bg-white/5">
                  <td className="px-4 py-3 font-medium">{targetOf(r.config.config)}</td>
                  <td className="px-4 py-3"><RunStatusChip status={r.status} /></td>
                  <td className="px-4 py-3 tabular-nums">{r.summary.counts?.confirmed ?? '–'}</td>
                  <td className="px-4 py-3 tabular-nums text-muted">{r.summary.states ?? '–'}</td>
                  <td className="px-4 py-3 tabular-nums text-muted">{r.summary.total_usd != null ? `$${r.summary.total_usd.toFixed(2)}` : '–'}</td>
                  <td className="px-4 py-3 text-muted">{ago(r.created)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Outlet, useParams } from 'react-router-dom'
import { api } from '../api'
import { useRunEvents } from '../hooks/useRunEvents'
import { paths } from '../paths'
import { useStore } from '../store'
import { ButtonLink, Empty } from '../components/ui'

/** Binds the store to the run in the URL and follows its event stream; every page under /runs/:run reads from it. */
export function RunLayout() {
  const { run = '' } = useParams()
  const runId = useStore(s => s.runId)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    setMissing(false)
    if (useStore.getState().runId !== run) useStore.getState().reset(run)
    api.run(run).catch(() => setMissing(true))
  }, [run])
  useRunEvents(missing || runId !== run ? null : run)

  if (missing) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <Empty title="No scan with this id" testid="run-missing" action={<ButtonLink to={paths.runs} kind="primary">See all results</ButtonLink>}>
          It may have been made on another machine, or the database was reset.
        </Empty>
      </div>
    )
  }
  return <Outlet />
}

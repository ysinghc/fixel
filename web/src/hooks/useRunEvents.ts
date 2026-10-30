import { useEffect } from 'react'
import { useStore } from '../store'

/** Follows a run's event stream. Reconnects with ?after=<last seq> so no event is lost or repeated; the store ignores any
 *  event whose seq it has already applied, so a replay from the start after a reload is harmless too. */
export function useRunEvents(runId: string | null) {
  const apply = useStore(s => s.applyEvent)
  useEffect(() => {
    if (!runId) return
    let last = 0
    let stop = false
    let es: EventSource | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    const open = () => {
      es = new EventSource(`/api/runs/${runId}/events?after=${last}`)
      es.onmessage = m => {
        const ev = JSON.parse(m.data)
        if (ev.seq > last) { last = ev.seq; apply(ev) }
      }
      es.onerror = () => {
        es?.close()
        if (!stop) timer = setTimeout(open, 1000)
      }
    }
    open()
    return () => { stop = true; es?.close(); if (timer) clearTimeout(timer) }
  }, [runId, apply])
}

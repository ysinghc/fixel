import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { paths } from '../paths'
import { api } from '../api'
import type { BenchLabelValue, BenchQueue, BenchRunRow, QueueItem } from '../types'
import { Button, Chip } from '../components/ui'

const LABELS: { value: BenchLabelValue; text: string; key: string; tone: string }[] = [
  { value: 'visible_defect', text: 'Visible defect', key: 'v', tone: 'bg-red-500/80 hover:bg-red-500 text-white' },
  { value: 'no_visible_defect', text: 'No visible defect', key: 'n', tone: 'bg-emerald-500/80 hover:bg-emerald-500 text-black' },
  { value: 'unsure', text: 'Unsure', key: 'u', tone: 'bg-amber-400/80 hover:bg-amber-400 text-black' },
]
const SQUARE: Record<string, string> = { visible_defect: 'bg-red-500', no_visible_defect: 'bg-emerald-500', unsure: 'bg-amber-400' }

/**
 * Blind labelling: the screen is shown with nothing that says whether a defect was injected, whether the page is
 * unmodified, or what Fixel found. The human answer is the ground truth behind the benchmark's headline numbers.
 */
export function LabelPage() {
  const [runs, setRuns] = useState<BenchRunRow[]>([])
  const [run, setRun] = useState('')
  const [q, setQ] = useState<BenchQueue | null>(null)
  const [i, setI] = useState(0)
  const [error, setError] = useState('')
  const [reviewing, setReviewing] = useState(false)

  useEffect(() => {
    api.bench().then(b => { setRuns(b.runs); if (b.runs[0]) setRun(r => r || b.runs[0].run) }).catch(e => setError(String(e.message)))
  }, [])
  useEffect(() => {
    if (!run) return
    let current = true                                    // ignore a late answer for a run no longer selected
    setQ(null)
    api.benchQueue(run).then(d => {
      if (!current) return
      setQ(d)
      const firstOpen = d.items.findIndex(x => !x.label)
      setI(firstOpen < 0 ? 0 : firstOpen)
    }).catch(e => { if (current) setError(String(e.message)) })
    return () => { current = false }
  }, [run])

  const items = q?.items ?? []
  const item: QueueItem | undefined = items[i]
  const done = items.filter(x => x.label).length
  const finished = items.length > 0 && done === items.length && !reviewing

  const go = useCallback((d: number) => setI(x => Math.max(0, Math.min(items.length - 1, x + d))), [items.length])
  const label = useCallback((value: BenchLabelValue) => {
    if (!q || !item) return
    setError('')
    const before = item.label
    const setLabel = (v: BenchLabelValue | null) => setQ(cur => cur && { ...cur, items: cur.items.map(x => (x.id === item.id ? { ...x, label: v } : x)) })
    setLabel(value)                                                         // optimistic: fast keypresses must not land on the same screen
    const next = items.findIndex((x, k) => k > i && !x.label)               // on to the next unlabelled screen
    setI(next >= 0 ? next : Math.min(items.length - 1, i + 1))
    api.benchLabel(q.run, item.id, value).catch(e => { setLabel(before); setError(`Not saved: ${(e as Error).message}`) })
  }, [q, item, items, i])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.tagName === 'SELECT' || t.tagName === 'INPUT' || e.metaKey || e.ctrlKey || e.altKey) return
      if (finished) return
      const l = LABELS.find(x => x.key === e.key)
      if (l) label(l.value)
      else if (e.key === 'ArrowRight' || e.key === 'j') go(1)
      else if (e.key === 'ArrowLeft' || e.key === 'k') go(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [label, go, finished])

  const split = useMemo(() => runs.find(r => r.run === run)?.split, [runs, run])

  if (!runs.length) {
    return (
      <div className="grid h-full place-items-center p-8" data-testid="label-view">
        <div className="max-w-md space-y-2 rounded-xl border border-line bg-panel p-6 text-sm text-zinc-300">
          <h2 className="text-base font-semibold">Nothing to label yet</h2>
          <p>Labels are the ground truth for the benchmark. Run one first:</p>
          <pre className="rounded bg-black/40 p-2 text-xs">fixel bench run --split test</pre>
          {error && <p className="text-xs text-red-300">{error}</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0" data-testid="label-view">
      <aside className="flex w-64 flex-none flex-col gap-3 overflow-y-auto border-r border-line bg-panel p-3">
        <select value={run} onChange={e => setRun(e.target.value)} data-testid="label-run" className="h-7 rounded-md border border-line bg-raised px-2 text-xs">
          {runs.map(r => <option key={r.run} value={r.run}>{r.run}</option>)}
        </select>
        <div className="flex flex-wrap items-center gap-1.5">
          {split === 'test'
            ? <Chip tone="amber" title="These labels feed the headline numbers">test split</Chip>
            : <Chip tone="zinc" title="A development run is for tuning; its labels are practice and are never a headline">development split (practice)</Chip>}
          <span className="text-xs tabular-nums text-zinc-300" data-testid="label-progress">{done} / {items.length} labelled</span>
        </div>
        <div className="h-1 overflow-hidden rounded bg-line"><div className="h-full bg-sky-500 transition-all" style={{ width: `${items.length ? (done / items.length) * 100 : 0}%` }} /></div>
        <div className="grid grid-cols-10 gap-1" data-testid="label-grid">
          {items.map((x, k) => (
            <button key={x.id} onClick={() => setI(k)} title={`#${x.n}${x.label ? ` · ${x.label.replace(/_/g, ' ')}` : ''}`} data-testid="label-item" data-label={x.label ?? ''}
              className={`h-4 rounded-sm ${x.label ? SQUARE[x.label] : 'bg-[#2a2f3b]'} ${k === i ? 'ring-2 ring-white' : ''}`} />
          ))}
        </div>
        <p className="text-[11px] leading-4 text-muted">{q?.question}</p>
        <p className="text-[11px] leading-4 text-muted">
          You are not told whether a screen was changed on purpose or what Fixel found. That is deliberate: it keeps the label honest.
        </p>
        <p className="text-[11px] leading-4 text-muted">Keys: <kbd>v</kbd> visible · <kbd>n</kbd> none · <kbd>u</kbd> unsure · <kbd>←</kbd>/<kbd>→</kbd> move.</p>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-none items-center gap-3 border-b border-line px-4 py-2">
          <span className="text-sm font-medium">Screen {item?.n ?? '–'} of {items.length}</span>
          {item && <span className="text-xs text-muted" data-testid="label-meta">{item.route} · {item.width}px · {item.theme} · {item.text_stress === 'pseudo' ? 'long text' : 'normal text'}</span>}
          <div className={`ml-auto flex items-center gap-2 ${finished ? 'invisible' : ''}`}>
            <Button onClick={() => go(-1)} disabled={i === 0} title="Previous (←)">←</Button>
            {LABELS.map(l => (
              <button key={l.value} onClick={() => label(l.value)} data-testid={`label-${l.key}`} data-on={item?.label === l.value} title={`${l.text} (${l.key})`}
                className={`h-7 rounded-md px-3 text-xs font-semibold ${l.tone} ${item?.label === l.value ? 'ring-2 ring-white' : ''}`}>
                {l.text} <kbd className="ml-1 opacity-70">{l.key}</kbd>
              </button>
            ))}
            <Button onClick={() => go(1)} disabled={i >= items.length - 1} title="Next (→)">→</Button>
          </div>
        </div>
        {error && <div className="bg-red-500/15 px-4 py-1.5 text-xs text-red-200" data-testid="label-error">{error}</div>}
        <div className="min-h-0 flex-1 overflow-auto bg-[#0a0c10] p-4">
          {finished ? (
            <div className="mx-auto mt-16 max-w-md space-y-4 text-center" data-testid="label-done">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-emerald-500 text-2xl font-bold text-black">✓</div>
              <h2 className="text-lg font-semibold">All {items.length} screens labelled</h2>
              <p className="text-sm text-muted">Thank you. These labels are the ground truth for the benchmark's headline numbers.</p>
              {split === 'test' && <p className="text-xs text-muted">To share them, run <code className="rounded bg-black/40 px-1">fixel bench export {run}</code> and push <code className="rounded bg-black/40 px-1">labels.json</code>.</p>}
              <div className="flex justify-center gap-2 pt-2">
                <Link to={paths.benchmark} className="inline-flex h-9 items-center rounded-lg bg-sky-500 px-4 text-sm font-medium text-white hover:bg-sky-400" data-testid="see-results">See the results</Link>
                <Button size="md" onClick={() => { setReviewing(true); setI(0) }}>Review my labels</Button>
              </div>
            </div>
          ) : !item ? <p className="text-sm text-muted">Loading…</p> : (
            <div className="mx-auto flex w-fit max-w-full flex-col" data-testid="label-screen" style={{ width: Math.min(item.width, 1400) }}>
              {item.tiles.map((sha, t) => (
                <img key={sha + t} src={api.artifact(sha)} alt={`screen ${item.n}, part ${t + 1}`} data-testid="label-tile"
                  className="block w-full border-b border-dashed border-line" />
              ))}
              <p className="py-2 text-center text-[11px] text-muted">The screen is shown as a user scrolls through it, {item.tiles.length} part{item.tiles.length === 1 ? '' : 's'}, at its real width.</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

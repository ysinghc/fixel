import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { widthRange } from '../fmt'
import { stateKeyFor, useStore, type Layers } from '../store'
import type { CandidateInfo, ElementBox, Finding, Status } from '../types'
import { Kbd } from './ui'

const STATUS_COLOR: Record<Status, string> = { confirmed: '#ef4444', needs_review: '#f59e0b', dismissed: '#64748b', not_observable: '#475569' }
const A = '#ef4444', B = '#3b82f6'

/** The finding's candidate in this tile, with the element rectangles the events carried. */
function boxesFor(f: Finding, stateKey: string, tile: number, cands: CandidateInfo[]): { id: number; rect: ElementBox['rect']; label: string }[] {
  const out: { id: number; rect: ElementBox['rect']; label: string }[] = []
  for (const c of f.candidates) {
    if (c.state_key !== stateKey || c.tile !== tile) continue
    const info = cands.find(x => x && x.tile === tile && x.elements.map(e => e.id).join() === c.elements.join())
    info?.elements.forEach((e, i) => out.push({ id: e.id, rect: e.rect, label: i === 0 ? 'A' : 'B' }))
  }
  return out
}

function Overlay() {
  const stateKey = useStore(s => s.stateKey)!
  const tile = useStore(s => s.tile)
  const st = useStore(s => s.states[stateKey])
  const cands = useStore(s => s.cands[stateKey]) ?? []
  const findings = useStore(s => s.findings)
  const detail = useStore(s => s.details[stateKey])
  const layers = useStore(s => s.layers)
  const sel = useStore(s => s.findingKey)
  const hover = useStore(s => s.hoverKey)
  const chip = useStore(s => s.hoverChip)
  const selectFinding = useStore(s => s.selectFinding)

  const vw = st.vw ?? st.width, vh = st.vh ?? st.height
  const elements = detail?.capture.tiles[tile]?.elements ?? []
  const here = cands.filter(c => c && c.tile === tile)
  const selected = sel ? findings[sel] : undefined

  const dom = useMemo(() => elements.filter(e => e.rect[2] > 0 && e.rect[0] < vw && e.rect[3] > 0 && e.rect[1] < vh).slice(0, 1500),
    [elements, vw, vh])

  const showSam = layers.sam || chip === 'pixels'
  const showCands = layers.candidates || chip === 'geometry'
  const showFindings = layers.findings || chip === 'spark'

  return (
    <svg viewBox={`0 0 ${vw} ${vh}`} className="pointer-events-none absolute inset-0 h-full w-full" data-testid="overlay">
      {layers.dom && dom.map(e => (
        <rect key={e.id} x={e.rect[0]} y={e.rect[1]} width={e.rect[2] - e.rect[0]} height={e.rect[3] - e.rect[1]}
          fill="none" stroke="#a1a1aa" strokeOpacity={0.35} strokeWidth={1} vectorEffect="non-scaling-stroke" />
      ))}

      {showSam && here.flatMap(c => (c.evidence?.sam_boxes ?? []).map((b, i) => (
        <g key={`${c.idx}-${i}`} data-testid="sam-box">
          <rect x={b[0]} y={b[1]} width={b[2] - b[0]} height={b[3] - b[1]} fill="#14b8a6" fillOpacity={0.2}
            stroke="#14b8a6" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          <text x={b[0] + 3} y={b[1] + 11} fontSize={Math.max(9, vw / 45)} fill="#5eead4" style={{ paintOrder: 'stroke' }} stroke="#000" strokeWidth={2}>
            SAM {b[4].toFixed(2)}
          </text>
        </g>
      )))}

      {showCands && here.map(c => c.elements.map((e, i) => (
        <rect key={`${c.idx}-${e.id}`} x={e.rect[0]} y={e.rect[1]} width={e.rect[2] - e.rect[0]} height={e.rect[3] - e.rect[1]}
          fill="none" stroke={i === 0 ? '#fbbf24' : '#60a5fa'} strokeDasharray="5 3" strokeWidth={1.5}
          strokeOpacity={chip === 'geometry' && selected ? 1 : 0.8} vectorEffect="non-scaling-stroke" />
      )))}

      {showFindings && Object.values(findings).map(f => {
        const bx = boxesFor(f, stateKey, tile, cands)
        if (!bx.length) return null
        const active = f.key === sel || f.key === hover
        const color = STATUS_COLOR[f.status]
        return (
          <g key={f.key} data-testid="finding-box" data-key={f.key} data-active={active}>
            {bx.map(b => (
              <g key={b.id}>
                <rect x={b.rect[0]} y={b.rect[1]} width={b.rect[2] - b.rect[0]} height={b.rect[3] - b.rect[1]}
                  fill={active ? (b.label === 'A' ? A : B) : color} fillOpacity={active ? 0.16 : 0.07}
                  stroke={b.label === 'A' || bx.length === 1 ? (active ? A : color) : B} strokeWidth={active ? 3 : 1.5}
                  strokeOpacity={active || f.status === 'confirmed' ? 1 : 0.55} vectorEffect="non-scaling-stroke"
                  className="pointer-events-auto cursor-pointer" onClick={() => selectFinding(f.key)} />
                {active && bx.length > 1 && (
                  <text x={b.rect[0] + 3} y={Math.max(11, b.rect[1] - 4)} fontSize={Math.max(10, vw / 40)} fontWeight={700}
                    fill={b.label === 'A' ? '#fca5a5' : '#93c5fd'} stroke="#000" strokeWidth={2} style={{ paintOrder: 'stroke' }}>{b.label}</text>
                )}
              </g>
            ))}
          </g>
        )
      })}
    </svg>
  )
}

const LAYERS: { key: keyof Layers; label: string; swatch: string; hint: string; help: string }[] = [
  { key: 'findings', label: 'Findings', swatch: '#ef4444', hint: '4', help: 'Outlines of findings; the selected one is filled' },
  { key: 'sam', label: 'SAM bounds', swatch: '#14b8a6', hint: '2', help: 'What SAM 3.1 says is painted inside each box' },
  { key: 'candidates', label: 'Geometry candidates', swatch: '#fbbf24', hint: '3', help: 'Every box the geometry checks flagged, before the pixels' },
  { key: 'dom', label: 'All page elements', swatch: '#a1a1aa', hint: '1', help: 'Every element box from the page snapshot' },
]

/** The overlay layers live behind one button: most people only need the finding outline (cognitive load). */
export function LayerMenu() {
  const layers = useStore(s => s.layers)
  const toggle = useStore(s => s.toggleLayer)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [])
  const on = LAYERS.filter(l => layers[l.key]).length
  return (
    <div className="relative" ref={ref} data-testid="layers">
      <button onClick={() => setOpen(o => !o)} data-testid="layers-button" aria-expanded={open}
        className="flex items-center gap-1.5 rounded-lg border border-line bg-raised px-2.5 py-1 text-xs text-zinc-300 hover:border-zinc-500">
        Layers <span className="tabular-nums text-muted">{on}</span> <span className="text-muted">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-72 rounded-xl border border-line bg-panel p-1.5 shadow-2xl shadow-black/60" role="menu">
          {LAYERS.map(l => (
            <button key={l.key} onClick={() => toggle(l.key)} data-testid={`layer-${l.key}`} data-on={layers[l.key]} role="menuitemcheckbox" aria-checked={layers[l.key]}
              className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-white/5">
              <span className="mt-0.5 grid h-4 w-4 flex-none place-items-center rounded border" style={{ borderColor: l.swatch, background: layers[l.key] ? l.swatch : 'transparent' }}>
                {layers[l.key] && <span className="text-[10px] font-bold text-black">✓</span>}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center text-xs font-medium text-zinc-200">{l.label}<span className="ml-auto"><Kbd>{l.hint}</Kbd></span></span>
                <span className="block text-[11px] text-muted">{l.help}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** Discrete matrix widths, with the selected finding's failing range shaded red. */
function WidthScrubber() {
  const run = useStore(s => s.run)!
  const states = useStore(s => s.states)
  const stateKey = useStore(s => s.stateKey)
  const route = useStore(s => s.route)
  const theme = useStore(s => s.theme)
  const stress = useStore(s => s.stress)
  const sel = useStore(s => s.findingKey)
  const finding = useStore(s => (s.findingKey ? s.findings[s.findingKey] : undefined))
  const selectState = useStore(s => s.selectState)
  const widths = [...run.widths].sort((a, b) => a - b)
  const cur = states[stateKey ?? '']?.width
  const idx = (w: number) => (widths.length < 2 ? 0 : widths.indexOf(w) / (widths.length - 1))
  const failing = finding ? [...new Set(finding.widths)].sort((a, b) => a - b) : []
  const lo = failing.length ? idx(failing[0]) : 0, hi = failing.length ? idx(failing[failing.length - 1]) : 0

  return (
    <div className="px-6 pb-3 pt-2" data-testid="scrubber">
      <div className="relative mx-3 h-7">
        <div className="absolute left-0 right-0 top-2.5 h-1.5 rounded-full bg-[#222836]" />
        {finding && failing.length > 0 && (
          <div data-testid="scrubber-fail" className="absolute top-2 h-2.5 rounded-full bg-red-500/60"
            style={{ left: `${lo * 100}%`, width: `${Math.max(hi - lo, 0.02) * 100}%`, transform: lo === hi ? 'translateX(-50%)' : undefined }}
            title={`${finding.type} fails at ${widthRange(finding.widths)}`} />
        )}
        {widths.map(w => {
          const key = stateKeyFor(states, route, w, theme, stress)
          const on = w === cur
          return (
            <button key={w} onClick={() => key && selectState(key)} disabled={!key || states[key]?.status === 'running'}
              style={{ left: `${idx(w) * 100}%` }} data-testid={`scrub-${w}`}
              className="absolute top-0 -translate-x-1/2 text-center disabled:opacity-40">
              <span className={`mx-auto block h-3.5 w-3.5 rounded-full border-2 ${on ? 'border-sky-300 bg-sky-500' : 'border-zinc-500 bg-ink hover:border-zinc-300'}`} style={{ marginTop: 6 }} />
              <span className={`mt-0.5 block text-[10px] tabular-nums ${on ? 'text-sky-200' : 'text-muted'}`}>{w}</span>
            </button>
          )
        })}
      </div>
      {sel && finding && <div className="mt-3 text-center text-[11px] text-muted">failing range of the selected finding: {widthRange(finding.widths)}</div>}
    </div>
  )
}

/** One rendered screen with its overlay. Reads the selected state and tile from the store. */
export function Viewer({ title }: { title?: string }) {
  const stateKey = useStore(s => s.stateKey)
  const st = useStore(s => (s.stateKey ? s.states[s.stateKey] : undefined))
  const tile = useStore(s => s.tile)
  const set = useStore(s => s.set)
  const loadDetail = useStore(s => s.loadDetail)
  useEffect(() => { if (stateKey) void loadDetail(stateKey) }, [stateKey, loadDetail])

  const t = st?.tiles[tile]
  if (!st || !t) {
    return <div className="grid min-h-0 flex-1 place-items-center p-8" data-testid="viewer-loading"><div className="skeleton h-64 w-48 rounded-lg" /></div>
  }
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col" data-testid="stage">
      <div className="flex flex-none flex-wrap items-center gap-3 px-4 py-2">
        <div className="min-w-0 text-xs" data-testid="state-label">
          {title && <span className="mr-2 font-medium text-zinc-200">{title}</span>}
          <span className="font-mono text-zinc-300">{st.route}</span>
          <span className="text-muted"> · {st.width}px · {st.theme} · {st.text_stress === 'pseudo' ? 'long text' : 'normal text'}</span>
        </div>
        {st.tiles.length > 1 && (
          <div className="flex items-center gap-1" data-testid="tiles" title="The page as a user scrolls it">
            {st.tiles.map(x => (
              <button key={x.index} onClick={() => set({ tile: x.index })} title={`scrolled ${x.scroll_y}px`}
                className={`rounded px-1.5 py-0.5 text-[11px] tabular-nums ${x.index === tile ? 'bg-white/15 text-white' : 'text-muted hover:text-zinc-200'}`}>
                {x.index + 1}
              </button>
            ))}
            <span className="pl-1 text-[11px] text-muted">of {st.tiles.length}</span>
          </div>
        )}
        <div className="ml-auto"><LayerMenu /></div>
      </div>
      <div className="relative min-h-0 flex-1 overflow-auto px-4 pb-2">
        <div className="mx-auto h-full" style={{ aspectRatio: `${st.vw ?? st.width} / ${st.vh ?? st.height}`, maxWidth: '100%', maxHeight: '100%' }}>
          <div className="relative h-full w-full overflow-hidden rounded-lg border border-line bg-white shadow-2xl shadow-black/50" data-testid="tile">
            <img key={t.sha} src={api.artifact(t.sha)} alt={`${st.route} at ${st.width}px`} className="absolute inset-0 h-full w-full" draggable={false} />
            <Overlay />
          </div>
        </div>
      </div>
      <WidthScrubber />
    </section>
  )
}

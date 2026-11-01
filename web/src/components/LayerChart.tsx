import { useState } from 'react'
import type { Rate } from '../types'

// One series, one hue (dataviz reference palette, dark slot 1; validated against the panel surface #12151b)
const BAR = '#3987e5'
const LEVEL: Record<string, string> = { geometry: 'Geometry', diff: '+ Pixel diff', sam: '+ SAM 3.1', spark: '+ Spark triage' }

/** Horizontal bars, one per detection layer, 0-100% on one axis, with the 95% interval as a thin whisker. */
export function LayerChart({ rows, testid }: { rows: { level: string; r: Rate | null }[]; testid?: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 560, labelW = 120, right = 80, rowH = 40, top = 18, bar = 16
  const x = (p: number) => labelW + p * (W - labelW - right)
  const H = top + rows.length * rowH + 6
  return (
    <div className="relative" data-testid={testid}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[640px]" role="img" aria-label="Share per detection layer">
        {[0, 0.25, 0.5, 0.75, 1].map(t => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top - 4} y2={H - 6} stroke="#252a35" strokeWidth={1} />
            <text x={x(t)} y={10} textAnchor="middle" fontSize={10} fill="#8b93a3">{t * 100}%</text>
          </g>
        ))}
        {rows.map((row, i) => {
          const y = top + i * rowH + (rowH - bar) / 2
          const r = row.r
          const w = r ? Math.max(0, x(r.p) - x(0)) : 0
          return (
            <g key={row.level} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} data-testid="chart-bar">
              <rect x={0} y={top + i * rowH} width={W} height={rowH} fill={hover === i ? 'rgba(255,255,255,0.03)' : 'transparent'} />
              <text x={labelW - 10} y={y + bar / 2 + 4} textAnchor="end" fontSize={12} fill="#e6e9ef">{LEVEL[row.level] ?? row.level}</text>
              {r ? (
                <>
                  {/* square at the baseline, 4px rounded at the data end */}
                  {w >= 4 && <path d={`M${x(0)},${y} h${w - 4} a4,4 0 0 1 4,4 v${bar - 8} a4,4 0 0 1 -4,4 h${-(w - 4)} z`} fill={BAR} />}
                  {w > 0 && w < 4 && <rect x={x(0)} y={y} width={w} height={bar} fill={BAR} />}
                  <line x1={x(r.lo)} x2={x(r.hi)} y1={y + bar / 2} y2={y + bar / 2} stroke="#e6e9ef" strokeOpacity={0.55} strokeWidth={1.5} />
                  <text x={x(Math.max(r.p, r.hi)) + 8} y={y + bar / 2 + 4} fontSize={12} fill="#e6e9ef">{Math.round(r.p * 100)}%</text>
                </>
              ) : <text x={x(0) + 6} y={y + bar / 2 + 4} fontSize={11} fill="#8b93a3">not measured</text>}
            </g>
          )
        })}
      </svg>
      {hover !== null && rows[hover].r && (
        <div className="pointer-events-none absolute right-0 top-0 rounded-lg border border-line bg-raised px-3 py-2 text-xs shadow-xl" data-testid="chart-tooltip">
          <div className="font-medium">{LEVEL[rows[hover].level]}</div>
          <div className="text-muted">{rows[hover].r!.k} of {rows[hover].r!.n} · {Math.round(rows[hover].r!.p * 100)}%</div>
          <div className="text-muted">95% interval {Math.round(rows[hover].r!.lo * 100)}–{Math.round(rows[hover].r!.hi * 100)}%</div>
        </div>
      )}
    </div>
  )
}

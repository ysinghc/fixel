import type { Evidence, Finding, StateInfo } from './types'

export const TYPE_LABEL: Record<string, string> = {
  viewport_protrusion: 'overflows viewport', element_protrusion: 'sticks out of its box', clipped_text: 'clipped text',
  collision: 'collision', occlusion: 'covered', small_target: 'small tap target', contrast: 'low contrast',
}

export const SEVERITY_COLOR: Record<number, string> = { 4: '#ef4444', 3: '#f97316', 2: '#eab308', 1: '#64748b' }

/** "src/components/Cart.tsx:42:7" -> "Cart.tsx:42" */
export function locLabel(loc: string): string {
  const m = loc.match(/([^/]+):(\d+):\d+$/)
  return m ? `${m[1]}:${m[2]}` : loc
}

export function widthRange(widths: number[]): string {
  if (!widths.length) return ''
  const a = Math.min(...widths), b = Math.max(...widths)
  return a === b ? `${a} px` : `${a}–${b} px`
}

export const pct = (x: number | null | undefined) => (x == null ? '–' : `${Math.round(x * 100)}%`)

/** The oracle and its number. */
export function geometryText(f: Finding): string {
  const m = f.candidates[0]?.metrics ?? {}
  switch (f.type) {
    case 'viewport_protrusion': return `overflows by ${Math.round(m.overflow_px ?? 0)} px`
    case 'element_protrusion': return `sticks out ${Math.round(m.protrude_px ?? 0)} px`
    case 'clipped_text': return `${Math.round(Math.max(m.hidden_x ?? 0, m.hidden_y ?? 0))} px hidden`
    case 'collision': return `overlap ${pct(m.overlap_frac)}`
    case 'occlusion': return `${pct(m.covered)} covered`
    case 'small_target': return `${Math.round(m.w ?? 0)}×${Math.round(m.h ?? 0)} px`
    case 'contrast': return 'axe-core: color-contrast'
    default: return f.type
  }
}

const ALWAYS_VISIBLE = new Set(['viewport_protrusion', 'clipped_text', 'contrast', 'small_target'])

/** SAM and the opacity diff: what is actually painted. */
export function pixelsText(f: Finding, ev: Evidence | undefined): string {
  if (!ev) return 'pending'
  const parts: string[] = []
  if (ev.opacity_diff != null) parts.push(`diff ${pct(ev.opacity_diff)}`)
  if (ev.sam_conf != null) parts.push(`SAM ${ev.sam_conf.toFixed(2)}`)
  if (!parts.length) return ALWAYS_VISIBLE.has(f.type) ? 'visible by definition' : 'no pixel evidence'
  return parts.join(' · ')
}

/** The evidence for the narrowest-width state where the finding reproduces. */
export function representative(f: Finding, states: Record<string, StateInfo>): { index: number } {
  let best = 0, bw = Infinity
  f.candidates.forEach((c, i) => {
    const w = states[c.state_key]?.width ?? Infinity
    if (w < bw) { bw = w; best = i }
  })
  return { index: best }
}

export function money(x: number): string {
  return x < 0.1 ? `$${x.toFixed(4)}` : `$${x.toFixed(2)}`
}

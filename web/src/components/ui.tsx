import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'

type Tone = 'zinc' | 'red' | 'amber' | 'green' | 'teal' | 'blue' | 'violet'
const TONES: Record<Tone, string> = {
  zinc: 'border-line bg-raised text-zinc-300', red: 'border-red-500/40 bg-red-500/10 text-red-300',
  amber: 'border-amber-500/40 bg-amber-500/10 text-amber-300', green: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  teal: 'border-teal-500/40 bg-teal-500/10 text-teal-300', blue: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  violet: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
}

export function Chip({ children, tone = 'zinc', title, onEnter, onLeave, className = '' }: {
  children: ReactNode; tone?: Tone; title?: string; onEnter?: () => void; onLeave?: () => void; className?: string
}) {
  return (
    <span title={title} onMouseEnter={onEnter} onMouseLeave={onLeave}
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] leading-4 ${TONES[tone]} ${className}`}>
      {children}
    </span>
  )
}

export function Dot({ color, pulse = false, size = 8 }: { color: string; pulse?: boolean; size?: number }) {
  return <span className={pulse ? 'pulse inline-block rounded-full' : 'inline-block rounded-full'}
    style={{ width: size, height: size, background: color, flex: 'none' }} />
}

const KINDS = {
  primary: 'bg-sky-400 text-black hover:bg-sky-300 disabled:bg-sky-400/30 disabled:text-black/60',
  ghost: 'border border-line bg-raised text-zinc-200 hover:bg-[#1f2430] disabled:opacity-40',
  danger: 'border border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20 disabled:opacity-40',
  success: 'bg-emerald-500 text-black hover:bg-emerald-400 disabled:opacity-40',
}
const SIZES = { sm: 'h-7 px-2.5 text-xs', md: 'h-9 px-3.5 text-sm', lg: 'h-11 px-5 text-sm' }

export function Button({ children, onClick, disabled, kind = 'ghost', size = 'sm', title, className = '', ...rest }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; kind?: keyof typeof KINDS; size?: keyof typeof SIZES; title?: string; className?: string
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick' | 'children' | 'className' | 'disabled' | 'title'>) {
  return (
    <button onClick={onClick} disabled={disabled} title={title} {...rest}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${SIZES[size]} ${KINDS[kind]} ${className}`}>
      {children}
    </button>
  )
}

export function ButtonLink({ to, children, kind = 'ghost', size = 'sm', className = '', ...rest }: {
  to: string; children: ReactNode; kind?: keyof typeof KINDS; size?: keyof typeof SIZES; className?: string; [k: string]: unknown
}) {
  return (
    <Link to={to} {...rest} className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors ${SIZES[size]} ${KINDS[kind]} ${className}`}>
      {children}
    </Link>
  )
}

/** A page's title row: what this page is for, in one line, and its one primary action on the right. */
export function PageHeader({ title, subtitle, back, actions, testid }: {
  title: ReactNode; subtitle?: ReactNode; back?: { to: string; label: string }; actions?: ReactNode; testid?: string
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end gap-4" data-testid={testid}>
      <div className="min-w-0 flex-1">
        {back && <Link to={back.to} className="mb-1 inline-block text-xs text-muted hover:text-zinc-200" data-testid="back"><span aria-hidden>← </span>{back.label}</Link>}
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-none items-center gap-2">{actions}</div>}
    </header>
  )
}

export function Card({ children, className = '', testid, title, aside }: { children: ReactNode; className?: string; testid?: string; title?: ReactNode; aside?: ReactNode }) {
  return (
    <section className={`rounded-xl border border-line bg-panel p-4 ${className}`} data-testid={testid}>
      {(title || aside) && (
        <div className="mb-3 flex items-center gap-2">
          {title && <h2 className="text-[13px] font-semibold">{title}</h2>}
          {aside && <div className="ml-auto">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

/** Tabs that sit under a page header. Each tab is one topic; the counts tell you where the work is. */
export function Tabs<T extends string>({ value, items, onChange, testid }: {
  value: T; items: { value: T; label: ReactNode; count?: number; testid?: string; title?: string }[]; onChange: (v: T) => void; testid?: string
}) {
  return (
    <div className="mb-4 flex gap-1 border-b border-line" role="tablist" data-testid={testid}>
      {items.map(i => (
        <button key={i.value} role="tab" aria-selected={value === i.value} onClick={() => onChange(i.value)} data-testid={i.testid} data-active={value === i.value}
          title={i.title}
          className={`-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${value === i.value ? 'border-sky-400 text-white' : 'border-transparent text-muted hover:text-zinc-200'}`}>
          {i.label}{i.count !== undefined && <span className={`ml-1.5 tabular-nums ${value === i.value ? 'text-sky-300' : 'text-zinc-500'}`}>{i.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Empty({ icon = '◫', title, children, action, testid }: { icon?: string; title: string; children?: ReactNode; action?: ReactNode; testid?: string }) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-line px-6 py-12 text-center" data-testid={testid}>
      <div className="max-w-md space-y-3">
        <div className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-sky-500/10 text-lg text-sky-300">{icon}</div>
        <h2 className="text-base font-semibold">{title}</h2>
        {children && <div className="text-sm text-muted">{children}</div>}
        {action && <div className="pt-1">{action}</div>}
      </div>
    </div>
  )
}

export function Progress({ value, total, tone = 'sky', testid, label = 'Progress' }: { value: number; total: number; tone?: 'sky' | 'emerald'; testid?: string; label?: string }) {
  const pct = total ? Math.min(100, (value / total) * 100) : 0
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-line" data-testid={testid} role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={total}>
      <div className={`h-full rounded-full transition-all duration-300 ${tone === 'sky' ? 'bg-sky-500' : 'bg-emerald-500'}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

const ICONS: Record<string, string> = {
  home: 'M3 10.5 12 3l9 7.5M5 9.5V21h5v-6h4v6h5V9.5',
  scan: 'M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M8 12h8',
  results: 'M4 6h16M4 12h16M4 18h10',
  label: 'M20 12 12 20l-8-8V4h8l8 8ZM8 8h.01',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
}
export function Icon({ name, className = 'h-[18px] w-[18px]' }: { name: keyof typeof ICONS | string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d={ICONS[name] ?? ''} />
    </svg>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-line bg-raised px-1 font-mono text-[10px] text-zinc-400">{children}</kbd>
}

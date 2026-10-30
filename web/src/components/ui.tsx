import type { ButtonHTMLAttributes, ReactNode } from 'react'

export function Chip({ children, tone = 'zinc', title, onEnter, onLeave, className = '' }: {
  children: ReactNode; tone?: 'zinc' | 'red' | 'amber' | 'green' | 'teal' | 'blue' | 'violet'; title?: string
  onEnter?: () => void; onLeave?: () => void; className?: string
}) {
  const tones = {
    zinc: 'border-line bg-raised text-zinc-300', red: 'border-red-500/40 bg-red-500/10 text-red-300',
    amber: 'border-amber-500/40 bg-amber-500/10 text-amber-300', green: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
    teal: 'border-teal-500/40 bg-teal-500/10 text-teal-300', blue: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
    violet: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
  }
  return (
    <span title={title} onMouseEnter={onEnter} onMouseLeave={onLeave}
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] leading-4 ${tones[tone]} ${className}`}>
      {children}
    </span>
  )
}

export function Dot({ color, pulse = false, size = 8 }: { color: string; pulse?: boolean; size?: number }) {
  return <span className={pulse ? 'pulse inline-block rounded-full' : 'inline-block rounded-full'}
    style={{ width: size, height: size, background: color, flex: 'none' }} />
}

export function Button({ children, onClick, disabled, kind = 'ghost', title, className = '', ...rest }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; kind?: 'primary' | 'ghost' | 'danger'; title?: string; className?: string
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick' | 'children' | 'className' | 'disabled' | 'title'>) {
  const kinds = {
    primary: 'bg-sky-500 text-white hover:bg-sky-400 disabled:bg-sky-500/30 disabled:text-white/50',
    ghost: 'border border-line bg-raised text-zinc-200 hover:bg-[#1f2430] disabled:opacity-40',
    danger: 'border border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20 disabled:opacity-40',
  }
  return (
    <button onClick={onClick} disabled={disabled} title={title} {...rest}
      className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors disabled:cursor-not-allowed ${kinds[kind]} ${className}`}>
      {children}
    </button>
  )
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string; disabled?: boolean }[]; onChange: (v: T) => void; label?: string
}) {
  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-[11px] uppercase tracking-wide text-muted">{label}</span>}
      <div className="inline-flex overflow-hidden rounded-md border border-line">
        {options.map(o => (
          <button key={o.value} disabled={o.disabled} onClick={() => onChange(o.value)}
            className={`px-2 py-1 text-xs transition-colors disabled:opacity-30 ${value === o.value ? 'bg-sky-500/20 text-sky-200' : 'bg-raised text-zinc-400 hover:text-zinc-200'}`}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

import { Chip } from './ui'

const RUN_STATUS: Record<string, { tone: 'zinc' | 'blue' | 'green' | 'red' | 'amber'; text: string }> = {
  running: { tone: 'blue', text: 'Running' }, done: { tone: 'green', text: 'Done' }, failed: { tone: 'red', text: 'Failed' },
  cancelled: { tone: 'zinc', text: 'Cancelled' }, stopped: { tone: 'amber', text: 'Stopped (budget)' }, budget: { tone: 'amber', text: 'Stopped (budget)' },
}

export function RunStatusChip({ status }: { status: string }) {
  const s = RUN_STATUS[status] ?? { tone: 'zinc' as const, text: status }
  return <Chip tone={s.tone} className="font-medium"><span data-testid="run-status">{s.text}</span></Chip>
}

export function SplitChip({ split }: { split: string | null | undefined }) {
  if (split === 'test') return <Chip tone="amber" title="Test split: its numbers are reported, never used for tuning">test split</Chip>
  if (split === 'demo') return <Chip tone="violet" title="Planted defects, made for the demo">demo app</Chip>
  if (split === 'development') return <Chip tone="zinc" title="Development split: used for tuning">dev split</Chip>
  return null
}

export function ago(ts: number): string {
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(ts * 1000).toLocaleDateString()
}

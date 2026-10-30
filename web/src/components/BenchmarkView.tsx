import { useEffect, useState } from 'react'
import { api } from '../api'

/** Honest placeholder: the benchmark harness is not built yet, and this says so rather than showing invented numbers. */
export function BenchmarkView() {
  const [b, setB] = useState<{ available: boolean; reason?: string } | null>(null)
  useEffect(() => { api.bench().then(setB).catch(() => setB({ available: false, reason: 'the API is not reachable' })) }, [])
  return (
    <div className="grid flex-1 place-items-center p-8" data-testid="bench">
      <div className="max-w-xl space-y-4 rounded-xl border border-line bg-panel p-6">
        <h2 className="text-base font-semibold">Benchmark</h2>
        <p className="text-sm text-zinc-300">{b?.available ? 'Results' : `Not available yet: ${b?.reason ?? 'loading…'}.`}</p>
        <p className="text-xs text-muted">
          When built, this tab shows detection precision and recall against human labels (test split only), an ablation of what each layer adds
          (geometry → + opacity diff → + SAM → + Spark), verified-fix rate and cost, and a <em>Roll a case</em> button that injects a random seeded mutation
          and detects and fixes it live. No figure is shown until it is measured.
        </p>
        <p className="text-xs text-muted">The <em>Mark wrong</em> button on a finding already records a human label for it, which is the ground truth this will use.</p>
      </div>
    </div>
  )
}

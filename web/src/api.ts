import type { BenchList, BenchMetrics, BenchQueue, StateDetail } from './types'

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch { /* not json */ }
    throw new Error(String(detail))
  }
  return r.json() as Promise<T>
}

const post = (url: string, body: unknown) =>
  j<any>(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }) // eslint-disable-line @typescript-eslint/no-explicit-any

export interface Target {
  config: string
  name: string
  split: string | null
  routes: string[]
  widths: number[]
  themes: string[]
  text_stress: string[]
  height: number
}
export interface AppConfig { mode: 'live' | 'record' | 'replay'; models_available: boolean; budget_usd: number }
export interface RunRow { id: string; kind: string; created: number; status: string; config: { config: string }; summary: { counts?: Record<string, number>; total_usd?: number } }

export const api = {
  config: () => j<AppConfig>('/api/config'),
  targets: () => j<Target[]>('/api/targets'),
  runs: () => j<RunRow[]>('/api/runs'),
  scan: (body: { config: string; routes?: string[]; models: boolean }) => post('/api/scans', body) as Promise<{ run_id: string }>,
  cancel: (runId: string) => post(`/api/runs/${runId}/cancel`, {}),
  state: (runId: string, key: string) => j<StateDetail>(`/api/runs/${runId}/states/${encodeURIComponent(key).replace(/%2F/g, '/')}`),
  fix: (runId: string, key: string, model?: string) => post('/api/fix', { run_id: runId, key, model }) as Promise<{ fix_id: string }>,
  label: (runId: string, key: string, label: string, note = '') => post('/api/labels', { run_id: runId, key, label, note }),
  labels: (runId: string) => j<{ key: string; label: string }[]>(`/api/labels?run_id=${runId}`),
  bench: () => j<BenchList>('/api/bench'),
  benchMetrics: (run: string) => j<BenchMetrics>(`/api/bench/${encodeURIComponent(run)}`),
  benchQueue: (run: string) => j<BenchQueue>(`/api/bench/${encodeURIComponent(run)}/queue`),
  benchLabel: (run: string, caseId: string, label: string) =>
    j<{ ok: boolean }>(`/api/bench/${encodeURIComponent(run)}/labels`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ case_id: caseId, label }) }),
  artifact: (sha: string) => `/api/artifacts/${sha}`,
  patchUrl: (fixId: string) => `/api/fixes/${fixId}/patch`,
}

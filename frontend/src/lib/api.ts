import type { AgentRun, Health, Preflight, WardrobeItem } from './types';

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch('/api/health').then((r) => json<Health>(r)),
  preflight: () => fetch('/api/health/apis').then((r) => json<Preflight>(r)),
  runs: (limit = 5) => fetch(`/api/stylist/runs?limit=${limit}`).then((r) => json<AgentRun[]>(r)),
  reset: () => fetch('/api/dev/reset', { method: 'POST' }).then((r) => json<{ items: number }>(r)),
  closet: () => fetch('/api/closet').then((r) => json<WardrobeItem[]>(r)),
  updateItem: (id: string, patch: Partial<WardrobeItem>) =>
    fetch(`/api/closet/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }).then((r) => json<WardrobeItem>(r)),
  deleteItem: (id: string) => fetch(`/api/closet/${id}`, { method: 'DELETE' }),
  startPlan: (message: string) =>
    fetch('/api/stylist/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    }).then((r) => json<{ run_id: string }>(r)),
  run: (id: string) => fetch(`/api/stylist/runs/${id}`).then((r) => json<AgentRun>(r)),
  scan: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return fetch('/api/closet/scan', { method: 'POST', body }).then((r) =>
      json<{ item: WardrobeItem; trace: import('./types').TraceStep[] }>(r),
    );
  },
};

export function daysAgo(iso: string | null): string {
  if (!iso) return 'Never worn';
  const days = Math.round((Date.now() - new Date(iso + 'T12:00:00').getTime()) / 86_400_000);
  if (days <= 0) return 'Worn today';
  if (days === 1) return 'Worn yesterday';
  return `Worn ${days} days ago`;
}

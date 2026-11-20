import type {
  AgentRun,
  BuyCheckResponse,
  CalendarResponse,
  DeviceLocation,
  GoogleCalendarStatus,
  Health,
  Paywall,
  Preflight,
  ShopResponse,
  WardrobeItem,
} from './types';

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

/** Thrown when the free monthly checks are used up (HTTP 402). */
export class PaywallError extends Error {
  readonly paywall: Paywall;
  constructor(paywall: Paywall) {
    super(`You've used your ${paywall.limit} free checks this month.`);
    this.paywall = paywall;
  }
}

/** FastAPI errors arrive as {"detail": "..."}; show just the message. */
async function errorText(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const detail = (JSON.parse(text) as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  } catch {
    // not JSON
  }
  return text || res.statusText;
}

export const api = {
  health: () => fetch('/api/health').then((r) => json<Health>(r)),
  calendar: (start: string, end: string, refresh = false) =>
    fetch(`/api/calendar?start=${start}&end=${end}${refresh ? '&refresh=true' : ''}`).then((r) => json<CalendarResponse>(r)),
  googleCalendarStatus: () => fetch('/api/calendar/google/status').then((r) => json<GoogleCalendarStatus>(r)),
  /** A full-page navigation (not fetch): the backend redirects to Google's consent screen and back. */
  googleCalendarConnectUrl: (returnTo: string) => `/api/calendar/google/connect?return_to=${encodeURIComponent(returnTo)}`,
  disconnectGoogleCalendar: () =>
    fetch('/api/calendar/google/disconnect', { method: 'POST' }).then((r) => json<GoogleCalendarStatus>(r)),
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
  startPlan: (message: string, location?: DeviceLocation | null) =>
    fetch('/api/stylist/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, location: location ? { lat: location.lat, lon: location.lon, city: location.city } : null }),
    }).then((r) => json<{ run_id: string }>(r)),
  reverseGeocode: (lat: number, lon: number) =>
    fetch(`/api/location/reverse?lat=${lat}&lon=${lon}`).then((r) => json<DeviceLocation>(r)),
  run: (id: string) => fetch(`/api/stylist/runs/${id}`).then((r) => json<AgentRun>(r)),
  scan: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return fetch('/api/closet/scan', { method: 'POST', body }).then((r) =>
      json<{ item: WardrobeItem; trace: import('./types').TraceStep[] }>(r),
    );
  },
  buyCheck: async (file: File): Promise<BuyCheckResponse> => {
    const body = new FormData();
    body.append('file', file);
    const res = await fetch('/api/buy-check', { method: 'POST', body });
    if (res.status === 402) throw new PaywallError((await res.json()) as Paywall);
    if (!res.ok) throw new Error(await errorText(res));
    return res.json() as Promise<BuyCheckResponse>;
  },
  shop: (category?: string | null, maxPrice?: number | null) => {
    const q = new URLSearchParams();
    if (category) q.set('category', category);
    if (maxPrice) q.set('max_price', String(maxPrice));
    return fetch(`/api/shop${q.size ? `?${q}` : ''}`).then((r) => json<ShopResponse>(r));
  },
  /** Dev/testing override: restores the free Should I Buy checks; the limit applies again after. */
  resetBuyChecks: () =>
    fetch('/api/dev/reset-buy-checks', { method: 'POST' }).then((r) =>
      json<{ checks_used: number; limit: number; pro: boolean }>(r),
    ),
  getBuyCheck: (id: string) => fetch(`/api/buy-check/${id}`).then((r) => json<BuyCheckResponse>(r)),
  keepBuyCheck: async (id: string): Promise<{ item: WardrobeItem }> => {
    const res = await fetch(`/api/buy-check/${id}/keep`, { method: 'POST' });
    if (!res.ok) throw new Error(await errorText(res));
    return res.json() as Promise<{ item: WardrobeItem }>;
  },
};

export function daysAgo(iso: string | null): string {
  if (!iso) return 'Never worn';
  const days = Math.round((Date.now() - new Date(iso + 'T12:00:00').getTime()) / 86_400_000);
  if (days <= 0) return 'Worn today';
  if (days === 1) return 'Worn yesterday';
  return `Worn ${days} days ago`;
}

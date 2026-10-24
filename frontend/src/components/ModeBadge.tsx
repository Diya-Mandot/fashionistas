import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { Health, Preflight } from '../lib/types';

/** Small, unobtrusive indicator so we never demo mocks as live. Click to run the preflight. */
export function ModeBadge({ light }: { light: boolean }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [open, setOpen] = useState(false);
  const [pf, setPf] = useState<Preflight | null>(null);
  const [checking, setChecking] = useState(false);
  const [resetMsg, setResetMsg] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  if (!health) return null;
  const live = health.key_configured && health.agents_mode === 'live' && health.decisions_mode === 'live';
  const label = live ? 'Live APIs' : health.key_configured ? `Mode: ${health.agents_mode}/${health.decisions_mode}` : 'Mock mode · no API key';

  const run = async () => {
    setChecking(true);
    try {
      setPf(await api.preflight());
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-bold ${
          live ? (light ? 'bg-white/20 text-white' : 'bg-sage-100 text-forest-mid') : 'bg-accent-light text-[#8A6236] ring-1 ring-sand/60'
        }`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${live ? 'bg-emerald' : 'bg-sand'}`} />
        {label}
      </button>
      {open && (
        <div className="absolute right-0 top-10 z-30 w-[300px] rounded-2xl bg-paper p-4 text-left shadow-2xl ring-1 ring-line">
          <p className="type-micro-dark mb-2">API preflight</p>
          <p className="type-body-sm mb-3">One tiny real call to each API. Run this before you demo.</p>
          <button type="button" onClick={run} disabled={checking} className="rounded-full bg-forest px-3.5 py-1.5 text-[12px] font-bold text-white disabled:opacity-60">
            {checking ? 'Checking…' : 'Run preflight'}
          </button>
          <button
            type="button"
            onClick={async () => {
              const r = await api.reset();
              setResetMsg(`Closet restored (${r.items} items), runs cleared`);
            }}
            className="ml-2 rounded-full px-3 py-1.5 text-[12px] font-semibold text-ink ring-1 ring-line hover:bg-white"
          >
            Reset demo data
          </button>
          {resetMsg && <p className="mt-2 text-[12px] text-forest-mid">{resetMsg}</p>}
          {pf && (
            <ul className="mt-3 flex flex-col gap-1.5 text-[12px]">
              {(['decisions', 'agents'] as const).map((k) => (
                <li key={k} className="flex items-start justify-between gap-2">
                  <span className="font-semibold capitalize text-ink">{k} API</span>
                  <span className={pf[k].ok ? 'text-forest-mid' : 'text-error'}>
                    {pf[k].ok ? `OK · ${pf[k].ms} ms` : pf[k].error}
                  </span>
                </li>
              ))}
              <li className="flex justify-between">
                <span className="font-semibold text-ink">Recorded live calls</span>
                <span className="text-muted">
                  {pf.recordings.decisions} decisions · {pf.recordings.agents} agent runs
                </span>
              </li>
              <li className="flex justify-between">
                <span className="font-semibold text-ink">Calendar</span>
                <span className="text-muted">{health.calendar ?? 'demo calendar'}</span>
              </li>
              <li className="flex justify-between">
                <span className="font-semibold text-ink">Google Vision</span>
                <span className="text-muted">{pf.vision_configured ? 'configured' : 'not set (local fallback)'}</span>
              </li>
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

import { useState } from 'react';
import type { Scores } from '../lib/types';

const CRITERIA: { key: keyof Omit<Scores, 'overall'>; label: string; meaning: string }[] = [
  { key: 'vibe', label: 'Vibe match', meaning: 'How well it matches the look you described' },
  { key: 'dress_code', label: 'Dress code', meaning: 'Fit for the event and its dress code' },
  { key: 'weather', label: 'Weather', meaning: 'Comfort for the temperature and rain chance' },
  { key: 'color', label: 'Color harmony', meaning: 'How well the colors work together' },
  { key: 'freshness', label: 'Freshness', meaning: 'Rotation: how recently these pieces were worn' },
];

/** Single-series horizontal bars (0–1), fixed criterion order, values in ink at the tip. */
export function ScoreBreakdown({ scores, compact = false }: { scores: Scores; compact?: boolean }) {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-2" role="table" aria-label="Decisions API score breakdown">
      {CRITERIA.map(({ key, label, meaning }) => {
        const v = Math.max(0, Math.min(1, scores[key]));
        return (
          <div
            key={key}
            role="row"
            className="group relative grid grid-cols-[96px_minmax(0,1fr)_36px] items-center gap-3"
            onMouseEnter={() => setHover(key)}
            onMouseLeave={() => setHover(null)}
          >
            <span role="rowheader" className={`${compact ? 'text-[12px]' : 'text-[13px]'} font-medium text-ink`}>
              {label}
            </span>
            <span role="cell" className="relative h-5">
              <span className="absolute inset-y-[6px] left-0 right-0 rounded-[4px] bg-sand-100" />
              <span
                className="absolute inset-y-[4px] left-0 rounded-r-[4px] bg-emerald-deep transition-[width] duration-500"
                style={{ width: `${v * 100}%`, maxHeight: 12 }}
              />
            </span>
            <span role="cell" className="text-right text-[12px] font-semibold tabular-nums text-ink">
              {v.toFixed(2)}
            </span>
            {hover === key && (
              <span className="pointer-events-none absolute -top-9 left-24 z-10 whitespace-nowrap rounded-lg bg-ink px-2.5 py-1.5 text-[11px] text-white shadow-lg">
                {label}: <b>{v.toFixed(2)}</b> · {meaning}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ScorePill({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-[rgba(52,211,153,0.18)] px-2.5 py-1 text-[12px] font-bold tabular-nums text-forest">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald" />
      {Math.round(value * 100)}
    </span>
  );
}

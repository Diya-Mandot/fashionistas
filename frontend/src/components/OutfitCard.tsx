import { useState } from 'react';
import { IoChevronDown, IoSwapHorizontalOutline } from 'react-icons/io5';
import type { OutfitPick, PlanEvent, WardrobeItem } from '../lib/types';
import { MicroChip } from './Chip';
import { ScoreBreakdown, ScorePill } from './ScoreBreakdown';

export function OutfitCard({ event, items }: { event: PlanEvent; items: Map<string, WardrobeItem> }) {
  const options: OutfitPick[] = [event.outfit, ...event.alternates].filter((o): o is OutfitPick => !!o);
  const [idx, setIdx] = useState(0);
  const [showWhy, setShowWhy] = useState(false);
  const pick = options[idx];

  return (
    <article className="glass overflow-hidden rounded-hero">
      <header className="flex items-start justify-between gap-3 px-5 pt-5">
        <div>
          <p className="type-micro mb-1">
            {event.time ? `${event.time} · ` : ''}
            {event.dress_code ?? 'Event'}
          </p>
          <h3 className="type-display-sm">{event.name}</h3>
        </div>
        {pick && <ScorePill value={pick.scores.overall} />}
      </header>

      {!pick ? (
        <p className="type-body-md px-5 pb-5 pt-3">No outfit could be built for this event.</p>
      ) : (
        <>
          <div className={`grid gap-2 px-5 pt-4 ${pick.item_ids.length > 4 ? 'grid-cols-3 sm:grid-cols-5' : 'grid-cols-2 sm:grid-cols-4'}`}>
            {pick.item_ids.map((id) => {
              const it = items.get(id);
              return (
                <figure key={id} className="overflow-hidden rounded-card bg-white/80">
                  <div className="aspect-[5/6] bg-sand-100">
                    {it && <img src={it.image_url} alt={it.name} className="h-full w-full object-cover" />}
                  </div>
                  <figcaption className="px-2.5 py-2 text-[12px] font-semibold leading-4 text-ink">{it?.name ?? 'Item'}</figcaption>
                </figure>
              );
            })}
          </div>

          <div className="px-5 pb-5 pt-4">
            <p className="type-body-md text-ink/80">{pick.rationale}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setShowWhy(!showWhy)}
                className="flex items-center gap-1 rounded-full bg-white/80 px-3 py-1.5 text-[12px] font-semibold text-ink ring-1 ring-line hover:bg-white"
              >
                Score breakdown <IoChevronDown className={`transition-transform ${showWhy ? 'rotate-180' : ''}`} />
              </button>
              {idx > 0 && <MicroChip tone="sand">Alternate {idx}</MicroChip>}
            </div>
            {showWhy && (
              <div className="mt-3 rounded-2xl bg-white/75 p-4">
                <p className="type-micro mb-3">Scored by the Decisions API</p>
                <ScoreBreakdown scores={pick.scores} />
              </div>
            )}

            {options.length > 1 && (
              <div className="mt-4">
                <p className="type-micro mb-2 flex items-center gap-1">
                  <IoSwapHorizontalOutline size={12} /> {options.length - 1} alternate{options.length > 2 ? 's' : ''}
                </p>
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {options.map((o, n) => (
                    <button
                      key={o.ref ?? n}
                      type="button"
                      onClick={() => setIdx(n)}
                      aria-label={`Show option ${n + 1}`}
                      className={`flex shrink-0 items-center gap-1 rounded-2xl p-1.5 pr-2.5 ring-2 transition ${
                        n === idx ? 'bg-white ring-emerald' : 'bg-white/60 ring-transparent hover:bg-white'
                      }`}
                    >
                      <span className="flex -space-x-3">
                        {o.item_ids.slice(0, 3).map((id) => (
                          <img key={id} src={items.get(id)?.image_url} alt="" className="h-10 w-9 rounded-lg object-cover ring-2 ring-white" />
                        ))}
                      </span>
                      <span className="ml-1 text-[11px] font-bold tabular-nums text-ink">{Math.round(o.scores.overall * 100)}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </article>
  );
}

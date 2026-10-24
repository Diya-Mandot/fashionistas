import { useState } from 'react';
import { IoCheckmark } from 'react-icons/io5';
import type { Plan, WardrobeItem } from '../lib/types';

export function PackingList({ plan, items }: { plan: Plan; items: Map<string, WardrobeItem> }) {
  const [packed, setPacked] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setPacked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <section className="glass rounded-hero p-5">
      <div className="mb-3 flex items-end justify-between">
        <div>
          <p className="type-micro-dark">Packing list</p>
          <p className="type-body-sm">
            {plan.packing_list.length} pieces · {packed.size} packed
          </p>
        </div>
      </div>
      <ul className="grid gap-2 sm:grid-cols-2">
        {plan.packing_list.map((p) => {
          const it = items.get(p.item_id);
          const done = packed.has(p.item_id);
          return (
            <li key={p.item_id}>
              <button
                type="button"
                onClick={() => toggle(p.item_id)}
                aria-pressed={done}
                className={`flex w-full items-center gap-3 rounded-2xl p-2 pr-3 text-left transition ${done ? 'bg-sage-100' : 'bg-white/70 hover:bg-white'}`}
              >
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${done ? 'border-forest bg-forest text-white' : 'border-sage-200 bg-white'}`}>
                  {done && <IoCheckmark size={13} />}
                </span>
                {it && <img src={it.image_url} alt="" className="h-11 w-10 rounded-lg object-cover" />}
                <span className="min-w-0">
                  <span className={`block text-[13px] font-semibold text-ink ${done ? 'line-through opacity-60' : ''}`}>{it?.name ?? p.item_id}</span>
                  <span className="block text-[11px] text-muted">{p.used_on.join(' · ')}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

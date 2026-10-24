import { IoAlertCircleOutline, IoOpenOutline, IoRefreshCircleOutline } from 'react-icons/io5';
import type { Gap } from '../lib/types';

export function GapCard({ gap }: { gap: Gap }) {
  const must = gap.severity === 'must-have';
  return (
    <article className="rounded-hero border border-sand/40 bg-accent-light/90 p-5 shadow-[0_8px_28px_rgba(20,50,40,0.08)]">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sand/25 text-[#8A6236]">
          <IoAlertCircleOutline size={20} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="type-micro mb-1 !text-[#8A6236]">
            Closet gap · {must ? 'Must-have' : gap.severity.replace('-', ' ')}
          </p>
          <h3 className="type-display-sm capitalize">{gap.need}</h3>
          <p className="type-body-md mt-1">{gap.reason}</p>
        </div>
      </div>
      {gap.suggestion && (
        <div className="mt-4 rounded-2xl bg-white/80 p-4">
          <p className="flex items-center gap-1.5 text-[13px] font-bold text-forest">
            <IoRefreshCircleOutline size={16} /> Shop it secondhand: {gap.suggestion.description}
          </p>
          <p className="type-body-sm mt-1">{gap.suggestion.why}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {gap.suggestion.links.map((l) => (
              <a
                key={l.site}
                href={l.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 rounded-full bg-forest px-3.5 py-1.5 text-[12px] font-semibold text-white hover:opacity-90"
              >
                {l.site} <IoOpenOutline size={12} />
              </a>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

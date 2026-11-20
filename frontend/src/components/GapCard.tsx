import { IoAlertCircleOutline, IoArrowForward, IoStorefrontOutline } from 'react-icons/io5';
import { Link } from 'react-router-dom';
import type { Gap } from '../lib/types';

const money = (n: number) => `$${Number.isInteger(n) ? n : n.toFixed(2)}`;

/** Shop page URL for a gap, optionally focused on one product. */
function shopUrl(category: string | null | undefined, focus?: string) {
  const q = new URLSearchParams();
  if (category) q.set('category', category);
  if (focus) q.set('focus', focus);
  q.set('from', 'stylist');
  return `/shop?${q}`;
}

export function GapCard({ gap }: { gap: Gap }) {
  const must = gap.severity === 'must-have';
  const picks = gap.partner_picks ?? [];
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
      <div className="mt-4 rounded-2xl bg-white/80 p-4">
        <p className="flex items-center gap-1.5 text-[13px] font-bold text-forest">
          <IoStorefrontOutline size={16} /> Shop it secondhand in Utah: {gap.need}
        </p>
        <p className="type-body-sm mt-1">
          {picks.length > 0
            ? `${picks.length} in-stock pick${picks.length === 1 ? '' : 's'} from Utah thrift and gear shops that work with your closet, ranked by outfits unlocked`
            : "None of the Utah thrift and gear shops we track has this in stock right now. Stock changes daily, so check back soon."}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {picks.map((p) => (
            <Link
              key={p.id}
              to={shopUrl(p.category ?? gap.shop_category, p.id)}
              className="flex items-center gap-1 rounded-full bg-forest px-3.5 py-1.5 text-[12px] font-semibold text-white hover:opacity-90"
            >
              {p.name} · {money(p.price)} <IoArrowForward size={12} />
            </Link>
          ))}
          {gap.shop_category && (
            <Link
              to={shopUrl(gap.shop_category)}
              className="flex items-center gap-1 rounded-full bg-white px-3.5 py-1.5 text-[12px] font-semibold text-forest ring-1 ring-forest/30 hover:bg-forest/5"
            >
              Browse all {gap.shop_category} <IoArrowForward size={12} />
            </Link>
          )}
        </div>
      </div>
    </article>
  );
}

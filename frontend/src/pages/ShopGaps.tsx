import { useEffect, useState } from 'react';
import { IoArrowBack, IoExtensionPuzzleOutline, IoShieldCheckmarkOutline } from 'react-icons/io5';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FilterChip } from '../components/Chip';
import { GlassPanel } from '../components/GlassPanel';
import { PageShell } from '../components/PageShell';
import { ProductCard } from '../components/ProductCard';
import { useToast } from '../components/Toast';
import { api } from '../lib/api';
import type { ShopGap, ShopProduct, ShopResponse } from '../lib/types';

const BUDGETS: { label: string; value: number | null }[] = [
  { label: 'Any price', value: null },
  { label: 'Under $75', value: 75 },
  { label: 'Under $100', value: 100 },
  { label: 'Under $150', value: 150 },
];

export function ShopGaps({ active = true }: { active?: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const category = params.get('category');
  const fromBuy = params.get('from') === 'buy';
  const [maxPrice, setMaxPrice] = useState<number | null>(null);
  const [data, setData] = useState<ShopResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast, show } = useToast();

  useEffect(() => {
    if (!active) return;
    let stale = false;
    setLoading(true);
    api
      .shop(category, maxPrice)
      .then((r) => {
        if (stale) return;
        setData(r);
        setError(null);
      })
      .catch((e: Error) => !stale && setError(e.message))
      .finally(() => !stale && setLoading(false));
    return () => {
      stale = true;
    };
  }, [active, category, maxPrice]);

  const setCategory = (c: string | null) => {
    const q = new URLSearchParams(location.search);
    if (c) q.set('category', c);
    else q.delete('category');
    navigate(`/shop${q.size ? `?${q}` : ''}`, { replace: true });
  };

  // Checkout is mocked; the commission screen arrives with the money surfaces (Phase 5).
  const buy = (p: ShopProduct) => show(`Demo: no real checkout for ${p.name}`);

  const products = data?.products ?? [];
  return (
    <PageShell>
      <div className="mb-6">
        <p className="type-micro mb-2">Partner stores</p>
        <h1 className="type-display-lg">Shop your gaps</h1>
        <p className="type-body-md mt-1 max-w-[620px]">
          Only pieces that work with what you already own, ranked by how many new outfits they unlock.
        </p>
        {fromBuy && (
          <Link
            to="/buy"
            className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-white/80 px-3.5 py-1.5 text-[13px] font-semibold text-ink ring-1 ring-line hover:bg-white"
          >
            <IoArrowBack size={14} /> Back to the item you checked
          </Link>
        )}
      </div>

      {data && data.gaps.length > 0 && (
        <GlassPanel radius="hero" className="mb-6 p-5">
          <p className="type-micro mb-3">Gaps in your closet</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.gaps.map((g) => (
              <GapTile
                key={g.label}
                gap={g}
                selected={category === g.category}
                filteredOut={!!category && category !== g.category}
                onPick={() => setCategory(g.category)}
              />
            ))}
          </div>
        </GlassPanel>
      )}

      <div className="-mx-5 mb-3 flex gap-2 overflow-x-auto px-5 pb-1 md:mx-0 md:flex-wrap md:px-0">
        <FilterChip active={!category} onClick={() => setCategory(null)}>
          all
        </FilterChip>
        {(data?.categories ?? []).map((c) => (
          <FilterChip key={c} active={category === c} onClick={() => setCategory(c)}>
            {c}
          </FilterChip>
        ))}
      </div>
      <div className="-mx-5 mb-6 flex gap-2 overflow-x-auto px-5 pb-1 md:mx-0 md:flex-wrap md:px-0">
        {BUDGETS.map((b) => (
          <FilterChip key={b.label} active={maxPrice === b.value} onClick={() => setMaxPrice(b.value)}>
            {b.label}
          </FilterChip>
        ))}
      </div>

      {error && <p className="type-body-md text-error">Couldn’t load the shop: {error}</p>}

      <div className={`grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
        {products.map((p) => (
          <ProductCard key={p.id} product={p} onBuy={buy} />
        ))}
      </div>

      {data && !loading && products.length === 0 && (
        <GlassPanel radius="hero" className="p-5">
          <p className="type-label-bold">Nothing here earns a place in your closet yet.</p>
          <p className="type-body-md mt-1">Try another category or a higher budget.</p>
        </GlassPanel>
      )}

      {data && (
        <p className="type-body-sm mt-8 flex items-start gap-2">
          <IoShieldCheckmarkOutline size={16} className="mt-0.5 shrink-0 text-forest-mid" />
          <span>
            {data.hidden_by_trust_rule > 0 &&
              `${data.hidden_by_trust_rule} item${data.hidden_by_trust_rule === 1 ? '' : 's'} hidden because ${
                data.hidden_by_trust_rule === 1 ? "it doesn't" : "they don't"
              } fit your closet. `}
            We only show products scoring {data.trust_min}+ against your closet, sponsored or not.
          </span>
        </p>
      )}
      {toast}
    </PageShell>
  );
}

function GapTile({
  gap,
  selected,
  filteredOut,
  onPick,
}: {
  gap: ShopGap;
  selected: boolean;
  /** Another category is filtered, so this gap's products aren't in the list. */
  filteredOut: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      className={`flex items-start gap-3 rounded-2xl p-3 text-left transition-colors ${
        selected ? 'bg-white ring-2 ring-emerald' : 'bg-white/70 hover:bg-white'
      }`}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-light text-[#8A6236]">
        <IoExtensionPuzzleOutline size={16} />
      </span>
      <span className="min-w-0">
        <span className="type-label-medium block capitalize">{gap.label}</span>
        <span className="type-body-sm block">
          {gap.status === 'empty' ? 'You have none' : `Only ${gap.count}`}
          {' · '}
          {filteredOut
            ? `Tap to shop ${gap.category}`
            : gap.products > 0
              ? `${gap.products} pick${gap.products === 1 ? '' : 's'} below`
              : 'Nothing in stock that fits yet'}
        </span>
      </span>
    </button>
  );
}

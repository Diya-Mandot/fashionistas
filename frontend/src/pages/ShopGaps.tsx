import { useEffect, useState } from 'react';
import { IoArrowBack, IoShieldCheckmarkOutline } from 'react-icons/io5';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FilterChip } from '../components/Chip';
import { GlassPanel } from '../components/GlassPanel';
import { PageShell } from '../components/PageShell';
import { ProductCard } from '../components/ProductCard';
import { useToast } from '../components/Toast';
import { api } from '../lib/api';
import type { ShopProduct, ShopResponse } from '../lib/types';

export function ShopGaps({ active = true }: { active?: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const category = params.get('category');
  const fromBuy = params.get('from') === 'buy';
  const fromStylist = params.get('from') === 'stylist';
  const focus = params.get('focus');
  const [data, setData] = useState<ShopResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast, show } = useToast();

  useEffect(() => {
    if (!active) return;
    let stale = false;
    setLoading(true);
    api
      .shop(category)
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
  }, [active, category]);

  // Opened from a Stylist gap pill: bring that product into view once it's loaded.
  useEffect(() => {
    if (!active || !focus || loading || !data) return;
    document.getElementById(`product-${focus}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [active, focus, loading, data]);

  const setCategory = (c: string | null) => {
    const q = new URLSearchParams(location.search);
    if (c) q.set('category', c);
    else q.delete('category');
    q.delete('focus');
    navigate(`/shop${q.size ? `?${q}` : ''}`, { replace: true });
  };

  // Thrift listings open on the store's own site; the mock catalog has no real checkout.
  const buy = (p: ShopProduct) => {
    if (p.url) window.open(p.url, '_blank', 'noopener,noreferrer');
    else show(`Demo: no real checkout for ${p.name}`);
  };

  const products = data?.products ?? [];
  const thrift = data?.source === 'thrift';
  return (
    <PageShell>
      <div className="mb-6">
        <p className="type-micro mb-2">{thrift ? 'Utah thrift stores' : 'Partner stores'}</p>
        <h1 className="type-display-lg">Shop your gaps</h1>
        {fromBuy && (
          <Link
            to="/buy"
            className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-white/80 px-3.5 py-1.5 text-[13px] font-semibold text-ink ring-1 ring-line hover:bg-white"
          >
            <IoArrowBack size={14} /> Back to the item you checked
          </Link>
        )}
        {fromStylist && (
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-white/80 px-3.5 py-1.5 text-[13px] font-semibold text-ink ring-1 ring-line hover:bg-white"
          >
            <IoArrowBack size={14} /> Back to your plan
          </button>
        )}
      </div>

      <div className="-mx-5 mb-6 flex gap-2 overflow-x-auto px-5 pb-1 md:mx-0 md:flex-wrap md:px-0">
        <FilterChip active={!category} onClick={() => setCategory(null)}>
          all
        </FilterChip>
        {(data?.categories ?? []).map((c) => (
          <FilterChip key={c} active={category === c} onClick={() => setCategory(c)}>
            {c}
          </FilterChip>
        ))}
      </div>

      {error && <p className="type-body-md text-error">Couldn’t load the shop: {error}</p>}

      <div className={`grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
        {products.map((p) => (
          <ProductCard key={p.id} product={p} onBuy={buy} focused={p.id === focus} />
        ))}
      </div>

      {data && !loading && products.length === 0 && (
        <GlassPanel radius="hero" className="p-5">
          <p className="type-label-bold">Nothing here earns a place in your closet yet.</p>
          <p className="type-body-md mt-1">Try another category.</p>
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

import { useEffect, useMemo, useState } from 'react';
import { IoAddOutline, IoArrowForward, IoBagHandleOutline, IoStorefrontOutline } from 'react-icons/io5';
import { Link, useLocation } from 'react-router-dom';
import { FilterChip } from '../components/Chip';
import { ItemCard } from '../components/ItemCard';
import { ItemDrawer } from '../components/ItemDrawer';
import { PageShell } from '../components/PageShell';
import { api } from '../lib/api';
import type { WardrobeItem } from '../lib/types';

const CATEGORY_FILTERS = ['all', 'tops', 'bottoms', 'dresses', 'outerwear', 'shoes', 'activewear', 'accessories', 'bags'];
const FORMALITY_FILTERS = ['any', 'casual', 'smart casual', 'business', 'formal'];

const SHOP_LINKS = [
  { to: '/buy', title: 'Should I buy?', blurb: 'Check a piece against your closet', icon: IoBagHandleOutline },
  { to: '/shop', title: 'Shop', blurb: 'Fill the gaps in your wardrobe', icon: IoStorefrontOutline },
];

export function Closet({ active = true }: { active?: boolean }) {
  const [items, setItems] = useState<WardrobeItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState('all');
  const [formality, setFormality] = useState('any');
  const [selected, setSelected] = useState<WardrobeItem | null>(null);

  useEffect(() => {
    if (active) api.closet().then(setItems).catch((e: Error) => setError(e.message));
  }, [active]);

  // /closet?item=itm_… opens that item (linked from Should I Buy This? duplicates).
  const linkedId = new URLSearchParams(useLocation().search).get('item');
  useEffect(() => {
    if (!active || !linkedId || !items) return;
    const found = items.find((i) => i.id === linkedId);
    if (found) setSelected(found);
  }, [active, linkedId, items]);

  const visible = useMemo(
    () =>
      (items ?? [])
        .filter(
          (i) => (category === 'all' || i.category === category) && (formality === 'any' || i.formality === formality),
        )
        .sort((a, b) => CATEGORY_FILTERS.indexOf(a.category) - CATEGORY_FILTERS.indexOf(b.category)),
    [items, category, formality],
  );

  const onDelete = async (item: WardrobeItem) => {
    await api.deleteItem(item.id);
    setItems((prev) => prev?.filter((i) => i.id !== item.id) ?? null);
    setSelected(null);
  };

  return (
    <PageShell>
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="type-micro mb-2">Your closet</p>
          <h1 className="type-display-lg">
            {items ? `${items.length} pieces` : 'Loading…'}
          </h1>
          <p className="type-body-md mt-1">Everything the stylist agent can pick from.</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {SHOP_LINKS.map(({ to, title, blurb, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className="group flex items-center gap-3 rounded-2xl border border-line-subtle bg-white/85 p-3 pr-4 shadow-sm backdrop-blur transition hover:-translate-y-0.5 hover:shadow-md"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-forest text-white">
                  <Icon size={20} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[14px] font-bold text-ink">{title}</span>
                  <span className="block text-[12px] text-ink/60">{blurb}</span>
                </span>
                <IoArrowForward size={16} className="text-ink/50 transition group-hover:translate-x-0.5 group-hover:text-ink" />
              </Link>
            ))}
          </div>
        </div>
        <Link
          to="/scan"
          className="flex items-center gap-2 self-start rounded-full bg-forest px-5 py-2.5 text-[14px] font-bold text-white hover:opacity-90 md:self-auto"
        >
          <IoAddOutline size={18} /> Scan an item
        </Link>
      </div>

      <div className="-mx-5 mb-3 flex gap-2 overflow-x-auto px-5 pb-1 md:mx-0 md:flex-wrap md:px-0">
        {CATEGORY_FILTERS.map((c) => (
          <FilterChip key={c} active={category === c} onClick={() => setCategory(c)}>
            {c}
          </FilterChip>
        ))}
      </div>
      <div className="-mx-5 mb-8 flex gap-2 overflow-x-auto px-5 pb-1 md:mx-0 md:flex-wrap md:px-0">
        {FORMALITY_FILTERS.map((f) => (
          <FilterChip key={f} active={formality === f} onClick={() => setFormality(f)}>
            {f === 'any' ? 'Any formality' : f}
          </FilterChip>
        ))}
      </div>

      {error && <p className="type-body-md text-error">Couldn’t load your closet: {error}</p>}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {visible.map((item) => (
          <ItemCard key={item.id} item={item} onClick={() => setSelected(item)} />
        ))}
      </div>
      {items && visible.length === 0 && (
        <p className="type-body-md py-16 text-center">Nothing matches those filters.</p>
      )}

      <ItemDrawer item={selected} onClose={() => setSelected(null)} onDelete={onDelete} />
    </PageShell>
  );
}

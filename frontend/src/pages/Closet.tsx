import { useEffect, useMemo, useState } from 'react';
import { IoAddOutline } from 'react-icons/io5';
import { Link } from 'react-router-dom';
import { FilterChip } from '../components/Chip';
import { ItemCard } from '../components/ItemCard';
import { ItemDrawer } from '../components/ItemDrawer';
import { PageShell } from '../components/PageShell';
import { api } from '../lib/api';
import type { WardrobeItem } from '../lib/types';

const CATEGORY_FILTERS = ['all', 'tops', 'bottoms', 'dresses', 'outerwear', 'shoes', 'activewear', 'accessories', 'bags'];
const FORMALITY_FILTERS = ['any', 'casual', 'smart casual', 'business', 'formal'];

export function Closet({
  active = true, revision, latestScanId,
}: { active?: boolean; revision: number; latestScanId: string | null }) {
  const [items, setItems] = useState<WardrobeItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState('all');
  const [formality, setFormality] = useState('any');
  const [selected, setSelected] = useState<WardrobeItem | null>(null);

  useEffect(() => {
    if (!active) return;
    let stopped = false;
    const refresh = async () => {
      try {
        const closet = await api.closet();
        if (!stopped) {
          setItems(closet);
          setError(null);
        }
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : String(e));
      }
    };
    void refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, 30_000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [active, revision]);

  const visible = useMemo(
    () =>
      (items ?? [])
        .filter(
          (i) => (category === 'all' || i.category === category) && (formality === 'any' || i.formality === formality),
        )
        .sort((a, b) => (
          Number(b.id === latestScanId) - Number(a.id === latestScanId)
          || CATEGORY_FILTERS.indexOf(a.category) - CATEGORY_FILTERS.indexOf(b.category)
        )),
    [items, category, formality, latestScanId],
  );
  const hiddenScan = items?.find((item) => item.id === latestScanId && !visible.some((shown) => shown.id === item.id));

  const onDelete = async (item: WardrobeItem) => {
    await api.deleteItem(item.id);
    setItems((prev) => prev?.filter((i) => i.id !== item.id) ?? null);
    setSelected(null);
  };

  return (
    <PageShell>
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="type-micro mb-2">Your closet</p>
          <h1 className="type-display-lg">
            {items ? `${items.length} pieces` : 'Loading…'}
          </h1>
          <p className="type-body-md mt-1">Everything the stylist agent can pick from.</p>
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
      {hiddenScan && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <p className="type-body-sm">{hiddenScan.name} was saved. Your current filters hide it.</p>
          <button
            type="button"
            className="text-sm font-semibold text-ocean-deep underline"
            onClick={() => { setCategory('all'); setFormality('any'); }}
          >
            Show scanned item
          </button>
        </div>
      )}

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

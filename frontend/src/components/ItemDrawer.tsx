import { useEffect } from 'react';
import { IoClose, IoHeart, IoTrashOutline } from 'react-icons/io5';
import { daysAgo } from '../lib/api';
import type { WardrobeItem } from '../lib/types';
import { MicroChip } from './Chip';

export function ItemDrawer({
  item,
  onClose,
  onDelete,
}: {
  item: WardrobeItem | null;
  onClose: () => void;
  onDelete?: (item: WardrobeItem) => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!item) return null;
  const rows: [string, string | null | undefined][] = [
    ['Category', `${item.category} · ${item.subcategory}`],
    ['Formality', item.formality],
    ['Style', item.style],
    ['Color', item.color],
    ['Season', item.season],
    ['Material', item.material],
    ['Brand', item.brand],
    ['Waterproof', item.waterproof ? 'Yes' : 'No'],
    ['Last worn', daysAgo(item.last_worn)],
    ['Times worn', String(item.number_of_times_worn)],
  ];

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label={item.name}>
      <button type="button" aria-label="Close" className="absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-[440px] flex-col overflow-y-auto bg-paper shadow-2xl">
        <div className="relative aspect-[5/6] w-full bg-sand-100">
          <img src={item.image_url} alt={item.name} className="h-full w-full object-cover" />
          <button
            type="button"
            onClick={onClose}
            className="glass absolute right-4 top-4 rounded-full p-2 text-ink"
            aria-label="Close"
          >
            <IoClose size={18} />
          </button>
        </div>
        <div className="flex flex-col gap-5 p-6">
          <div>
            <p className="type-micro mb-1">{item.brand ?? 'Closet item'}</p>
            <h2 className="type-display-md flex items-center gap-2">
              {item.name}
              {item.is_favorite && <IoHeart className="text-forest" size={18} />}
            </h2>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <MicroChip>{item.category}</MicroChip>
              <MicroChip tone="green">{item.formality}</MicroChip>
              {item.waterproof && <MicroChip tone="ocean">Waterproof</MicroChip>}
            </div>
          </div>
          <dl className="divide-y divide-line-subtle rounded-card border border-line-subtle bg-white">
            {rows.map(([k, v]) => (
              <div key={k} className="flex items-center justify-between px-4 py-3">
                <dt className="type-body-sm">{k}</dt>
                <dd className="type-label-medium capitalize">{v || '—'}</dd>
              </div>
            ))}
          </dl>
          {onDelete && (
            <button
              type="button"
              onClick={() => onDelete(item)}
              className="flex items-center justify-center gap-2 self-start rounded-full px-4 py-2 text-[13px] font-semibold text-error hover:bg-error/5"
            >
              <IoTrashOutline size={16} /> Remove from closet
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}

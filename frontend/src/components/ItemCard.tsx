import { IoHeart } from 'react-icons/io5';
import type { WardrobeItem } from '../lib/types';
import { MicroChip } from './Chip';

export function ItemCard({ item, onClick }: { item: WardrobeItem; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="glass group flex flex-col overflow-hidden rounded-card text-left transition-transform hover:-translate-y-0.5"
    >
      <div className="relative aspect-[5/6] w-full overflow-hidden bg-sand-100">
        <img
          src={item.image_url}
          alt={item.name}
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        />
        {item.is_favorite && (
          <span className="absolute right-3 top-3 rounded-full bg-white/80 p-1.5 text-forest">
            <IoHeart size={12} />
          </span>
        )}
        {item.source === 'scan' && (
          <span className="absolute left-3 top-3">
            <MicroChip tone="ocean">Scanned</MicroChip>
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 bg-white/70 p-3.5">
        <p className="type-label-bold leading-tight">{item.name}</p>
        <div className="flex flex-wrap gap-1">
          <MicroChip>{item.category}</MicroChip>
          <MicroChip tone="green">{item.formality}</MicroChip>
          {item.season && <MicroChip tone="sand">{item.season.split(',')[0]}</MicroChip>}
        </div>
      </div>
    </button>
  );
}

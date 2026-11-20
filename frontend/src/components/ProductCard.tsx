import { IoBagHandleOutline, IoExtensionPuzzleOutline } from 'react-icons/io5';
import type { ShopProduct } from '../lib/types';

// Swatch colors for products without a photo yet. Matched in order, so
// "navy" wins over "blue" and "off-white" over "white".
const SWATCHES: [string, string][] = [
  ['navy', '#24324A'], ['charcoal', '#3A3D42'], ['black', '#1E1E1E'], ['off-white', '#EFEAE0'], ['cream', '#EFE6D2'],
  ['ivory', '#F2EDE1'], ['white', '#F4F4F2'], ['grey', '#9A9C9E'], ['gray', '#9A9C9E'], ['camel', '#B98A57'],
  ['tan', '#C6A57C'], ['khaki', '#BFAE85'], ['beige', '#D8C8AA'], ['brown', '#6E4B33'], ['olive', '#6B7046'],
  ['sage', '#A6B49A'], ['green', '#3E7A55'], ['teal', '#2F7C7A'], ['seafoam', '#8FC9B5'], ['blue', '#4E79A7'],
  ['red', '#B23A33'], ['rust', '#A5532E'], ['pink', '#D98BA0'], ['purple', '#7A5A99'], ['yellow', '#D9B44A'],
];

function swatch(color: string | null | undefined): string {
  const c = (color ?? '').toLowerCase();
  return SWATCHES.find(([k]) => c.includes(k))?.[1] ?? '#E6DFD2';
}

function ProductImage({ image, color, name, className }: { image: string | null; color: string | null; name: string; className: string }) {
  return image ? (
    <img src={image} alt={name} loading="lazy" className={`${className} object-cover`} />
  ) : (
    <div role="img" aria-label={`${name} (photo coming soon)`} className={className} style={{ backgroundColor: swatch(color) }} />
  );
}

function Sponsored() {
  return (
    <span className="rounded-full bg-white/90 px-2 py-[3px] text-[9px] font-bold uppercase tracking-[1.4px] text-muted ring-1 ring-line">
      Sponsored
    </span>
  );
}

const money = (n: number) => `$${Number.isInteger(n) ? n : n.toFixed(2)}`;

export function ProductCard({
  product,
  onBuy,
  focused = false,
}: {
  product: ShopProduct;
  onBuy: (p: ShopProduct) => void;
  /** Opened from a Stylist gap: highlight it. */
  focused?: boolean;
}) {
  const unlocks = product.outfit_count_label;
  return (
    <article
      id={`product-${product.id}`}
      className={`flex scroll-mt-24 flex-col overflow-hidden rounded-card bg-white/80 shadow-[0_8px_28px_rgba(20,50,40,0.08)] ${
        focused ? 'ring-2 ring-emerald' : 'ring-1 ring-white/60'
      }`}
    >
      <div className="relative">
        <ProductImage image={product.image} color={product.color} name={product.name} className="aspect-square w-full bg-sand-100" />
        {product.sponsored && (
          <span className="absolute right-2 top-2">
            <Sponsored />
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col p-2.5">
        <p className="font-display text-[15px] font-bold leading-5 text-forest">
          Unlocks {unlocks} outfit{product.outfit_count === 1 ? '' : 's'}
        </p>
        {product.fills.length > 0 && (
          <p className="mt-0.5 flex items-start gap-1 text-[11px] font-semibold leading-4 text-forest-mid">
            <IoExtensionPuzzleOutline size={12} className="mt-0.5 shrink-0" /> Fills: {product.fills.join(', ')}
          </p>
        )}
        <h3 className="mt-1.5 line-clamp-2 text-[13px] font-semibold leading-[18px] text-ink">{product.name}</h3>
        <p className="mt-0.5 truncate text-[11px] leading-4 text-ink/80">
          {product.store}
          {product.store_location && <span className="text-muted"> · {product.store_location}</span>}
        </p>
        {product.sizes && product.sizes.length > 0 && (
          <p className="truncate text-[11px] leading-4 text-muted">Size {product.sizes.join(', ')}</p>
        )}
        <div className="mt-auto flex items-center justify-between gap-2 pt-2">
          <span className="text-[14px] font-bold tabular-nums text-ink">{money(product.price)}</span>
          <button
            type="button"
            onClick={() => onBuy(product)}
            className="flex items-center gap-1 rounded-full bg-forest px-2.5 py-1 text-[11px] font-bold text-white hover:opacity-90"
          >
            <IoBagHandleOutline size={12} /> {product.url ? 'View' : 'Buy'}
          </button>
        </div>
      </div>
    </article>
  );
}

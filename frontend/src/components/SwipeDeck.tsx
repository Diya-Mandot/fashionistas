import { Children, useCallback, useRef, useState, type PointerEvent, type ReactNode } from 'react';
import { IoChevronBack, IoChevronForward } from 'react-icons/io5';

const CARD = 'min(calc(100vw - 72px), 440px)';
const SWIPE_PX = 50; // mouse drag distance that counts as a swipe
const CLICK_SLOP_PX = 6; // movement beyond this is a drag, not a click

/**
 * Horizontally swipeable cards, laid out from the left edge; as many as fit are visible.
 * Touch and trackpad use native scroll-snap; mouse users can drag, use the arrows, the dots,
 * or ← / → when the deck is focused.
 * Give it a new React `key` to start again from the first card (e.g. when a new batch loads).
 */
export function SwipeDeck({ children, label }: { children: ReactNode; label: string }) {
  const cards = Children.toArray(children);
  const count = cards.length;
  const ref = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const [atEnd, setAtEnd] = useState(false);
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ x: number; scroll: number; moved: number; id: number } | null>(null);
  const suppressClick = useRef(false);

  const go = useCallback(
    (i: number) => {
      const el = ref.current;
      const target = Math.max(0, Math.min(count - 1, i));
      const card = el?.children[target] as HTMLElement | undefined;
      if (!el || !card) return;
      el.scrollTo({ left: card.offsetLeft, behavior: 'smooth' });
      setIndex(target);
    },
    [count],
  );

  // The current card is the one nearest the left edge; at the far end, the last one.
  const onScroll = () => {
    const el = ref.current;
    if (!el || drag.current) return;
    const end = el.scrollLeft + el.clientWidth >= el.scrollWidth - 4;
    setAtEnd(end);
    if (end) {
      setIndex(count - 1);
      return;
    }
    let best = 0;
    let bestDist = Infinity;
    Array.from(el.children).forEach((c, i) => {
      const d = Math.abs((c as HTMLElement).offsetLeft - el.scrollLeft);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    setIndex(best);
  };

  // Mouse drag (touch already swipes natively).
  const onPointerDown = (e: PointerEvent) => {
    if (e.pointerType !== 'mouse' || e.button !== 0 || !ref.current) return;
    drag.current = { x: e.clientX, scroll: ref.current.scrollLeft, moved: 0, id: e.pointerId };
  };
  const onPointerMove = (e: PointerEvent) => {
    const d = drag.current;
    const el = ref.current;
    if (!d || !el) return;
    d.moved = e.clientX - d.x;
    if (!dragging && Math.abs(d.moved) > CLICK_SLOP_PX) {
      setDragging(true);
      el.setPointerCapture(d.id);
    }
    if (Math.abs(d.moved) > CLICK_SLOP_PX) el.scrollLeft = d.scroll - d.moved;
  };
  const endDrag = () => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (Math.abs(d.moved) > CLICK_SLOP_PX) {
      suppressClick.current = true;
      setTimeout(() => (suppressClick.current = false), 0);
    }
    setDragging(false);
    if (Math.abs(d.moved) > SWIPE_PX) go(index + (d.moved < 0 ? 1 : -1));
    else if (Math.abs(d.moved) > CLICK_SLOP_PX) go(index);
  };

  return (
    <div role="region" aria-roledescription="carousel" aria-label={label}>
      <div
        ref={ref}
        tabIndex={0}
        onScroll={onScroll}
        onKeyDown={(e) => {
          if (e.key === 'ArrowRight') {
            e.preventDefault();
            go(index + 1);
          } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            go(index - 1);
          }
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDragStart={(e) => e.preventDefault()}
        className={`no-scrollbar relative flex gap-4 overflow-x-auto py-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald/60 ${
          dragging ? 'cursor-grabbing select-none' : 'snap-x snap-mandatory cursor-grab'
        }`}
      >
        {cards.map((card, i) => (
          <div
            key={i}
            role="group"
            aria-roledescription="slide"
            aria-label={`${i + 1} of ${count}`}
            onClickCapture={(e) => {
              if (suppressClick.current) {
                e.preventDefault();
                e.stopPropagation();
              }
            }}
            className="flex shrink-0 snap-start"
            style={{ width: CARD }}
          >
            {card}
          </div>
        ))}
      </div>

      {count > 1 && (
        <div className="mt-3 flex items-center justify-center gap-4">
          <DeckArrow label="Previous" onClick={() => go(index - 1)} disabled={index === 0}>
            <IoChevronBack size={18} />
          </DeckArrow>
          <div className="flex items-center gap-2">
            {cards.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => go(i)}
                aria-label={`Go to ${i + 1} of ${count}`}
                aria-current={i === index}
                className={`h-2 rounded-full transition-all ${i === index ? 'w-6 bg-forest' : 'w-2 bg-ink/25 hover:bg-ink/40'}`}
              />
            ))}
          </div>
          <DeckArrow label="Next" onClick={() => go(index + 1)} disabled={index === count - 1 || atEnd}>
            <IoChevronForward size={18} />
          </DeckArrow>
        </div>
      )}
    </div>
  );
}

function DeckArrow({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="flex h-9 w-9 items-center justify-center rounded-full bg-white/85 text-ink ring-1 ring-line transition hover:bg-white disabled:opacity-35"
    >
      {children}
    </button>
  );
}

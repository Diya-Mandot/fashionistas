import type { ReactNode } from 'react';

type Tone = 'neutral' | 'green' | 'sand' | 'ocean';

const TONES: Record<Tone, string> = {
  neutral: 'bg-sand-100 text-ink',
  green: 'bg-sage-100 text-forest-mid',
  sand: 'bg-accent-light text-[#8A6236]',
  ocean: 'bg-[rgba(91,141,184,0.16)] text-ocean-deep',
};

export function MicroChip({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-[3px] text-[9px] font-bold uppercase tracking-[1.6px] ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

export function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`whitespace-nowrap rounded-full border px-4 py-2 text-[13px] font-semibold capitalize transition-colors ${
        active
          ? 'border-forest bg-forest text-white'
          : 'border-white/60 bg-white/55 text-ink backdrop-blur hover:bg-white/80'
      }`}
    >
      {children}
    </button>
  );
}

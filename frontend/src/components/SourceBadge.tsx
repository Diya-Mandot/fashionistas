import type { ApiSource } from '../lib/types';

const STYLES: Record<string, { label: string; cls: string }> = {
  live: { label: 'Live', cls: 'bg-sage-100 text-forest-mid' },
  replay: { label: 'Replayed live call', cls: 'bg-[rgba(91,141,184,0.16)] text-ocean-deep' },
  mock: { label: 'Mock', cls: 'bg-accent-light text-[#8A6236] ring-1 ring-sand/60' },
  rule: { label: 'Rule', cls: 'bg-sand-100 text-muted' },
  local: { label: 'Local', cls: 'bg-sand-100 text-muted' },
};

export function SourceBadge({ source }: { source?: ApiSource | string | null }) {
  if (!source) return null;
  const s = STYLES[source] ?? STYLES.local;
  return (
    <span className={`inline-flex rounded-full px-2 py-[2px] text-[9px] font-bold uppercase tracking-[1.4px] ${s.cls}`}>
      {s.label}
    </span>
  );
}

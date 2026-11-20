import { IoAlertCircle, IoCheckmarkCircle, IoCloseCircle } from 'react-icons/io5';
import type { Verdict } from '../lib/types';

// Brand colors only (theme/colors.ts): forest/emerald for yes, warm sand for
// maybe, the error red for skip. Each pairs a tinted fill with a text color
// that keeps 4.5:1 contrast on it.
const VERDICTS: Record<Verdict, { label: string; cls: string; Icon: typeof IoCheckmarkCircle }> = {
  great_buy: { label: 'Great buy', cls: 'bg-sage-100 text-forest-mid ring-emerald/40', Icon: IoCheckmarkCircle },
  maybe: { label: 'Maybe', cls: 'bg-accent-light text-[#8A6236] ring-sand/60', Icon: IoAlertCircle },
  skip: { label: 'Skip', cls: 'bg-[rgba(180,35,24,0.08)] text-error ring-error/30', Icon: IoCloseCircle },
};

export function verdictLabel(v: Verdict): string {
  return VERDICTS[v].label;
}

export function VerdictBadge({ verdict, score }: { verdict: Verdict; score?: number }) {
  const { label, cls, Icon } = VERDICTS[verdict];
  return (
    <span className={`inline-flex items-center gap-2 rounded-full px-4 py-2 ring-1 ${cls}`}>
      <Icon size={20} aria-hidden />
      <span className="font-display text-[18px] font-bold leading-none">{label}</span>
      {score != null && (
        <span className="ml-1 border-l border-black/15 pl-2 text-[13px] font-bold tabular-nums opacity-80" aria-label={`Score ${score} out of 100`}>
          {score}/100
        </span>
      )}
    </span>
  );
}

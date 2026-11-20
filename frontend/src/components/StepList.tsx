import { useEffect, useState } from 'react';
import type { TraceStep } from '../lib/types';
import { JsonBlock } from './JsonBlock';
import { SourceBadge } from './SourceBadge';
import { StepIcon } from './StepIcon';

const REVEAL_MS = 450;
const PENDING_MS = 1100;

/**
 * Reveals a finished request's trace one step at a time, and cycles a
 * "what's happening" label while the request is still running.
 */
export function useStepReveal(trace: TraceStep[], working: boolean, pendingSteps: string[]) {
  const [shown, setShown] = useState(0);
  const [pendingIdx, setPendingIdx] = useState(0);

  useEffect(() => {
    if (!working) return;
    setPendingIdx(0);
    setShown(0);
    const t = setInterval(() => setPendingIdx((i) => Math.min(i + 1, pendingSteps.length - 1)), PENDING_MS);
    return () => clearInterval(t);
  }, [working, pendingSteps.length]);

  useEffect(() => {
    if (shown >= trace.length) return;
    const t = setTimeout(() => setShown((n) => n + 1), REVEAL_MS);
    return () => clearTimeout(t);
  }, [shown, trace.length]);

  const allShown = !working && trace.length > 0 && shown >= trace.length;
  const pending = working ? pendingSteps[pendingIdx] : trace.length > 0 && !allShown ? 'Writing up…' : null;
  return { shown, allShown, pending };
}

/** The numbered step list used by Scan and Should I Buy This?. */
export function StepList({ trace, shown, pending }: { trace: TraceStep[]; shown: number; pending: string | null }) {
  const [openStep, setOpenStep] = useState<string | null>(null);
  return (
    <ol className="flex flex-col gap-3">
      {trace.slice(0, shown).map((s, i) => (
        <li key={s.id} className="animate-[fadeUp_.35s_ease-out] rounded-2xl bg-white/70 p-3">
          <button
            type="button"
            onClick={() => setOpenStep(openStep === s.id ? null : s.id)}
            className="flex w-full items-start gap-3 text-left"
          >
            <StepIcon step={s} />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="type-micro !tracking-[2px]">Step {i + 1}</span>
                <SourceBadge source={s.source} />
                {s.duration_ms != null && <span className="text-[11px] text-faint">{s.duration_ms} ms</span>}
              </span>
              <span className="type-label-medium mt-0.5 block">{s.title}</span>
              {s.detail && <span className="type-body-sm block">{s.detail}</span>}
            </span>
          </button>
          {openStep === s.id && (
            <div className="mt-3 flex flex-col gap-2 pl-11">
              <JsonBlock label="Request" value={s.args} />
              <JsonBlock label="Response" value={s.result} />
            </div>
          )}
        </li>
      ))}
      {pending && (
        <li className="flex items-center gap-3 rounded-2xl bg-white/50 p-3">
          <span className="h-8 w-8 animate-pulse rounded-full bg-sage-100" />
          <span className="type-body-md">{pending}</span>
        </li>
      )}
    </ol>
  );
}

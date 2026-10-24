import { useEffect, useRef, useState } from 'react';
import { IoChevronDown, IoTimeOutline } from 'react-icons/io5';
import type { AgentRun, TraceStep } from '../lib/types';
import { JsonBlock } from './JsonBlock';
import { ScoreBreakdown } from './ScoreBreakdown';
import { SourceBadge } from './SourceBadge';
import { StepIcon } from './StepIcon';

const API_LABEL: Record<string, string> = {
  build_and_score_outfits: 'Decisions API',
  find_closet_gaps: 'Decisions API',
  get_weather_forecast: 'Open-Meteo',
  read_calendar: 'Calendar',
  query_closet: 'Closet',
  suggest_secondhand_item: 'Secondhand',
  submit_plan: 'Validation',
};

function stepLabel(s: TraceStep): string {
  if (s.kind === 'input') return 'API input';
  if (s.tool) return `Tool · ${API_LABEL[s.tool] ?? s.tool}`;
  if (s.kind === 'thinking' || s.kind === 'message') return 'Agents API';
  return s.kind;
}

export function AgentTrace({ run }: { run: AgentRun | null }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [collapsed, setCollapsed] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const steps = run?.trace ?? [];
  const running = run?.status === 'running';

  useEffect(() => {
    if (running) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [steps.length, running]);

  const total = steps.find((s) => s.kind === 'final')?.duration_ms;
  const toolCount = steps.filter((s) => s.tool).length;

  return (
    <section className="glass flex flex-col rounded-hero p-5" aria-label="Agent trace">
      <button type="button" onClick={() => setCollapsed(!collapsed)} className="flex items-center justify-between text-left">
        <span>
          <span className="type-micro-dark block">Agent trace</span>
          <span className="type-body-sm">
            {running ? 'Working…' : `${toolCount} tool calls`}
            {total != null && ` · ${(total / 1000).toFixed(1)}s total`}
          </span>
        </span>
        <span className="flex items-center gap-2">
          {run?.sources?.agent && <SourceBadge source={run.sources.agent} />}
          <IoChevronDown className={`transition-transform ${collapsed ? '' : 'rotate-180'}`} />
        </span>
      </button>

      {!collapsed && (
        <ol className="mt-4 flex flex-col">
          {steps.map((s, i) => {
            const isOpen = open[s.id] ?? false;
            const expandable = s.args != null || s.result != null || s.decision?.winner_scores;
            return (
              <li key={s.id} className="relative flex animate-[fadeUp_.35s_ease-out] gap-3 pb-4">
                {i < steps.length - 1 && <span className="absolute left-4 top-9 h-[calc(100%-28px)] w-px bg-line" />}
                <span className={s.status === 'running' ? 'animate-pulse' : ''}>
                  <StepIcon step={s} />
                </span>
                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    disabled={!expandable}
                    onClick={() => setOpen({ ...open, [s.id]: !isOpen })}
                    className="w-full text-left disabled:cursor-default"
                  >
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="type-micro !tracking-[2px]">
                        Step {i + 1} · {stepLabel(s)}
                      </span>
                      <SourceBadge source={s.source} />
                      {s.duration_ms != null && s.kind !== 'final' && (
                        <span className="flex items-center gap-0.5 text-[11px] tabular-nums text-faint">
                          <IoTimeOutline size={11} /> {s.duration_ms < 1000 ? `${s.duration_ms} ms` : `${(s.duration_ms / 1000).toFixed(1)} s`}
                        </span>
                      )}
                    </span>
                    <span className={`mt-0.5 block text-[14px] leading-5 ${s.kind === 'input' ? 'font-semibold text-ink' : 'font-medium text-ink'}`}>
                      {s.kind === 'input' ? `“${s.detail}”` : s.title}
                    </span>
                    {s.kind !== 'input' && s.detail && <span className="type-body-sm mt-0.5 block line-clamp-3">{s.detail}</span>}
                    {expandable && (
                      <span className="mt-1 inline-block text-[12px] font-semibold text-ocean-deep">
                        {isOpen ? 'Hide details' : 'Show request & response'}
                      </span>
                    )}
                  </button>
                  {s.decision?.winner_scores && (
                    <div className="mt-3 rounded-2xl bg-white/75 p-3">
                      <p className="type-micro mb-2">
                        Winner · {s.decision.candidates_scored} scored · {s.decision.questions} Decisions questions
                      </p>
                      <ScoreBreakdown scores={s.decision.winner_scores} compact />
                    </div>
                  )}
                  {isOpen && (
                    <div className="mt-3 flex flex-col gap-2">
                      <JsonBlock label="Request" value={s.args} />
                      <JsonBlock label="Response" value={s.result} />
                    </div>
                  )}
                </div>
              </li>
            );
          })}
          {running && (
            <li className="flex items-center gap-3 pb-2">
              <span className="h-8 w-8 animate-pulse rounded-full bg-sage-100" />
              <span className="type-body-md">The agent is deciding what to do next…</span>
            </li>
          )}
          <div ref={endRef} />
        </ol>
      )}
    </section>
  );
}

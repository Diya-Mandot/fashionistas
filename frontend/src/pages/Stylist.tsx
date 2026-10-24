import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { IoArrowForward, IoRainyOutline, IoSparklesOutline } from 'react-icons/io5';
import { useSearchParams } from 'react-router-dom';
import { AgentTrace } from '../components/AgentTrace';
import { DayTabs } from '../components/DayTabs';
import { GapCard } from '../components/GapCard';
import { GlassPanel } from '../components/GlassPanel';
import { LocationChip } from '../components/LocationChip';
import { NavBar } from '../components/NavBar';
import { OutfitCard } from '../components/OutfitCard';
import { PackingList } from '../components/PackingList';
import { api } from '../lib/api';
import type { AgentRun, DeviceLocation, WardrobeItem } from '../lib/types';
import { useDeviceLocation } from '../lib/useDeviceLocation';
import { HERO_IMAGE } from '../theme/brand';

const POLL_MS = 700;

export function Stylist() {
  const [params, setParams] = useSearchParams();
  const [message, setMessage] = useState('');
  const [run, setRun] = useState<AgentRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [closet, setCloset] = useState<WardrobeItem[]>([]);
  const [day, setDay] = useState(0);
  const pollRef = useRef<number | null>(null);
  const geo = useDeviceLocation();
  const runId = params.get('run');

  const items = useMemo(() => new Map(closet.map((i) => [i.id, i])), [closet]);

  useEffect(() => {
    api.closet().then(setCloset).catch(() => undefined);
  }, []);

  const stopPolling = () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = null;
  };

  const follow = useCallback((id: string) => {
    stopPolling();
    const tick = async () => {
      try {
        const r = await api.run(id);
        setRun(r);
        setMessage((m) => m || r.message);
        if (r.status !== 'running') {
          stopPolling();
          api.closet().then(setCloset).catch(() => undefined);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        stopPolling();
      }
    };
    tick();
    pollRef.current = window.setInterval(tick, POLL_MS);
  }, []);

  useEffect(() => {
    if (runId) follow(runId);
    else setRun(null);
    return stopPolling;
  }, [runId, follow]);

  const onSubmit = async (e?: FormEvent) => {
    e?.preventDefault();
    const text = message.trim();
    if (!text) return;
    setError(null);
    setDay(0);
    setRun(null);
    try {
      const { run_id } = await api.startPlan(text, geo.location);
      setParams({ run: run_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const started = Boolean(runId);
  const plan = run?.plan ?? null;
  const days = plan?.days ?? [];
  const activeDay = days[Math.min(day, Math.max(0, days.length - 1))];

  return (
    <div className="relative min-h-screen">
      {/* Backdrop */}
      <div className={`${started ? 'fixed' : 'absolute'} inset-0 -z-10 h-full min-h-screen`}>
        <img src={HERO_IMAGE} alt="" className="h-full w-full object-cover" />
        <div
          className={
            started
              ? 'absolute inset-0 bg-gradient-to-b from-[rgba(250,249,246,0.55)] via-[rgba(250,249,246,0.85)] to-paper'
              : 'absolute inset-0 bg-gradient-to-b from-black/55 via-black/30 to-black/65'
          }
        />
      </div>
      <NavBar overlay dark={!started} />

      {!started ? (
        <section className="mx-auto flex min-h-screen w-full max-w-[880px] flex-col justify-center px-5 pb-16 pt-28 md:px-10">
          <p className="type-micro mb-4 text-white/80">Context-aware stylist</p>
          <h1 className="font-display text-[40px] font-bold leading-[44px] tracking-[-1px] text-white md:text-[56px] md:leading-[60px] md:tracking-[-1.4px]">
            Tell me the plan and the vibe.
            <br />
            <span className="text-sand">I’ll pack your closet for it.</span>
          </h1>
          <p className="type-body-lg mt-4 max-w-[560px] text-white/80">
            An agent checks the weather, reads your calendar and searches your closet, then lets a decision engine
            score every outfit.
          </p>
          <PromptBox message={message} setMessage={setMessage} onSubmit={onSubmit} dark geo={geo} />
          {error && <p className="mt-3 text-[13px] text-white">Couldn’t start: {error}</p>}
        </section>
      ) : (
        <main className="mx-auto max-w-[1360px] px-5 pb-24 pt-24 md:px-10">
          <PromptBox message={message} setMessage={setMessage} onSubmit={onSubmit} compact busy={run?.status === 'running'} geo={geo} />

          <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(360px,1fr)]">
            {/* Left: plan */}
            <div className="flex min-w-0 flex-col gap-5">
              {!plan ? (
                <PlanSkeleton failed={run?.status === 'failed'} error={run?.error ?? error} />
              ) : (
                <>
                  <header>
                    <p className="type-micro mb-1">
                      {plan.trip.city} · {fmt(plan.trip.start)} – {fmt(plan.trip.end)}
                    </p>
                    <h1 className="type-display-lg">{plan.trip.summary.charAt(0).toUpperCase() + plan.trip.summary.slice(1)}</h1>
                    {plan.gaps.some((g) => g.severity === 'must-have') && (
                      <p className="type-body-md mt-1 flex items-center gap-1.5">
                        <IoRainyOutline /> {plan.gaps.filter((g) => g.severity === 'must-have').length} must-have gap
                        {plan.gaps.filter((g) => g.severity === 'must-have').length > 1 ? 's' : ''} flagged below
                      </p>
                    )}
                  </header>
                  <DayTabs days={days} active={day} onChange={setDay} />
                  {activeDay && (
                    <div className="flex flex-col gap-5">
                      {activeDay.events.map((ev) => (
                        <OutfitCard key={`${activeDay.date}-${ev.name}`} event={ev} items={items} />
                      ))}
                    </div>
                  )}
                  {plan.gaps.map((g) => (
                    <GapCard key={g.need} gap={g} />
                  ))}
                  <PackingList plan={plan} items={items} />
                </>
              )}
            </div>

            {/* Right: trace */}
            <aside className="lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto">
              <AgentTrace run={run} />
            </aside>
          </div>
        </main>
      )}
    </div>
  );
}

function fmt(iso: string) {
  return new Date(iso + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

function PromptBox({
  message,
  setMessage,
  onSubmit,
  dark = false,
  compact = false,
  busy = false,
  geo,
}: {
  message: string;
  setMessage: (s: string) => void;
  onSubmit: (e?: FormEvent) => void;
  dark?: boolean;
  compact?: boolean;
  busy?: boolean;
  geo: { location: DeviceLocation | null; status: string; locate: () => void; clear: () => void };
}) {
  return (
    <GlassPanel radius="hero" className={compact ? 'p-2.5' : 'mt-10 p-3 md:p-4'}>
      <form onSubmit={onSubmit} className={compact ? 'flex flex-col gap-2 md:flex-row md:items-center' : ''}>
        <label htmlFor="prompt" className="sr-only">
          Where are you headed?
        </label>
        <textarea
          id="prompt"
          rows={compact ? 1 : 3}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) onSubmit();
          }}
          placeholder="Where are you headed? Tell me the plan and the vibe."
          className={`w-full resize-none rounded-card bg-white/85 px-5 font-sans text-ink placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-emerald/60 ${
            compact ? 'py-3 text-[15px] leading-6' : 'py-4 text-[16px] leading-6'
          }`}
        />
        <div className={compact ? 'flex shrink-0 items-center gap-2' : 'mt-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between'}>
          {compact && (
            <span className="hidden lg:block">
              <LocationChip location={geo.location} status={geo.status} onLocate={geo.locate} onClear={geo.clear} dark={false} />
            </span>
          )}
          {!compact && (
            <div className="flex flex-wrap items-center gap-2">
              <LocationChip location={geo.location} status={geo.status} onLocate={geo.locate} onClear={geo.clear} dark={dark} />
            </div>
          )}
          <button
            type="submit"
            disabled={!message.trim() || busy}
            className="flex items-center justify-center gap-2 rounded-full bg-forest px-6 py-3 text-[15px] font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <IoSparklesOutline size={18} />
            {busy ? 'Planning…' : compact ? 'Re-plan' : 'Plan my outfits'}
            {!busy && <IoArrowForward size={16} />}
          </button>
        </div>
      </form>
    </GlassPanel>
  );
}

function PlanSkeleton({ failed, error }: { failed: boolean; error: string | null }) {
  if (failed) {
    return (
      <GlassPanel radius="hero" className="p-6">
        <p className="type-display-sm">The agent couldn’t finish this plan.</p>
        <p className="type-body-md mt-1">{error ?? 'See the trace for details.'}</p>
      </GlassPanel>
    );
  }
  return (
    <div className="flex flex-col gap-5" aria-busy="true">
      <div>
        <p className="type-micro mb-2">Building your plan</p>
        <p className="type-display-md">The agent is gathering context…</p>
        <p className="type-body-md mt-1">Follow along in the trace: every tool call and decision appears as it happens.</p>
      </div>
      <div className="flex gap-2">
        {[0, 1, 2].map((n) => (
          <div key={n} className="glass h-[70px] w-[110px] animate-pulse rounded-2xl" />
        ))}
      </div>
      {[0, 1].map((n) => (
        <div key={n} className="glass rounded-hero p-5">
          <div className="h-3 w-24 animate-pulse rounded bg-white/70" />
          <div className="mt-2 h-5 w-48 animate-pulse rounded bg-white/70" />
          <div className="mt-4 grid grid-cols-4 gap-2">
            {[0, 1, 2, 3].map((k) => (
              <div key={k} className="aspect-[5/6] animate-pulse rounded-card bg-white/60" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

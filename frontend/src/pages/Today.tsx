import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  IoCalendarOutline,
  IoCheckmarkCircle,
  IoChevronDown,
  IoCloudOutline,
  IoRainyOutline,
  IoRefreshOutline,
  IoShuffleOutline,
  IoSnowOutline,
  IoSunnyOutline,
} from 'react-icons/io5';
import { MicroChip } from '../components/Chip';
import { GlassPanel } from '../components/GlassPanel';
import { LocationChip } from '../components/LocationChip';
import { PageShell } from '../components/PageShell';
import { ScoreBreakdown, ScorePill } from '../components/ScoreBreakdown';
import { SwipeDeck } from '../components/SwipeDeck';
import { useToast } from '../components/Toast';
import { api } from '../lib/api';
import type { DailyOutfit, DailyResponse, DailyWeather, GoogleCalendarStatus, WardrobeItem } from '../lib/types';
import { useDeviceLocation } from '../lib/useDeviceLocation';

const EVERYDAY = 'everyday';

function isoDay(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function time12(t: string | null) {
  if (!t) return 'All day';
  const [h, m] = t.split(':').map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

function WeatherIcon({ w, size = 28 }: { w: DailyWeather | null; size?: number }) {
  if (!w) return <IoCloudOutline size={size} />;
  if (w.snow) return <IoSnowOutline size={size} />;
  if ((w.precip_pct ?? 0) >= 50) return <IoRainyOutline size={size} />;
  if (/cloud|overcast|fog/i.test(w.summary ?? '')) return <IoCloudOutline size={size} />;
  return <IoSunnyOutline size={size} />;
}

const sameSet = (a: string[] | null, b: string[]) => !!a && a.length === b.length && b.every((id) => a.includes(id));

export function Today({ active = true }: { active?: boolean }) {
  const geo = useDeviceLocation();
  const [day] = useState(() => isoDay(new Date()));
  const [data, setData] = useState<DailyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [eventId, setEventId] = useState<string | undefined>(undefined);
  const [seen, setSeen] = useState<string[][]>([]);
  const [worn, setWorn] = useState<string[] | null>(null);
  const [wearing, setWearing] = useState<string | null>(null);
  const [google, setGoogle] = useState<GoogleCalendarStatus | null>(null);
  const { toast, show } = useToast();
  const attempt = useRef(0);

  const load = useCallback(
    async (opts: { eventId?: string; exclude?: string[][]; refresh?: boolean } = {}) => {
      const mine = ++attempt.current;
      setLoading(true);
      setError(null);
      try {
        const loc = geo.location;
        const res = await api.daily({
          date: day,
          ...(loc ? { lat: loc.lat, lon: loc.lon, city: loc.city } : {}),
          event_id: opts.eventId,
          exclude: opts.exclude,
          refresh: opts.refresh,
        });
        if (mine !== attempt.current) return;
        setData(res);
        setWorn(res.worn_item_ids);
      } catch (e) {
        if (mine === attempt.current) setError(e instanceof Error ? e.message : 'Something went wrong.');
      } finally {
        if (mine === attempt.current) setLoading(false);
      }
    },
    [day, geo.location],
  );

  // Load when the tab is first opened, and again if the location changes.
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    const key = geo.location ? `${geo.location.lat},${geo.location.lon}` : 'home';
    if (!active || loadedFor.current === key) return;
    loadedFor.current = key;
    setSeen([]);
    load({ eventId });
    api.googleCalendarStatus().then(setGoogle).catch(() => setGoogle(null));
  }, [active, geo.location, load, eventId]);

  const items = useMemo(() => new Map<string, WardrobeItem>((data?.items ?? []).map((i) => [i.id, i])), [data]);
  const occasionId = data?.occasion?.id ?? EVERYDAY;

  const pickOccasion = (id: string) => {
    if (id === occasionId || loading) return;
    setEventId(id);
    setSeen([]);
    load({ eventId: id });
  };

  const showDifferent = () => {
    if (!data) return;
    const next = [...seen, ...data.outfits.map((o) => o.item_ids)];
    setSeen(next);
    load({ eventId: occasionId, exclude: next });
  };

  const wear = async (o: DailyOutfit) => {
    setWearing(o.ref);
    try {
      const res = await api.wearOutfit(day, o.item_ids);
      setWorn(res.worn_item_ids);
      show(`Wearing ${o.title} today. Marked as worn in your closet.`);
    } catch (e) {
      show(e instanceof Error ? e.message : "Couldn't save that. Try again.");
    } finally {
      setWearing(null);
    }
  };

  const connect = () => {
    window.location.href = api.googleCalendarConnectUrl(window.location.origin + window.location.pathname);
  };

  const dateLabel = new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
  const w = data?.weather ?? null;

  return (
    <PageShell>
      <header className="mb-6">
        <p className="type-micro mb-2">{dateLabel}</p>
        <h1 className="type-display-lg">Today’s outfit</h1>
        <p className="type-body-lg mt-1">Five looks from your closet for today’s weather and what’s on your calendar. Pick one to wear.</p>
      </header>

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        {/* Weather */}
        <GlassPanel radius="hero" className="flex flex-col gap-3 p-5">
          <p className="type-micro">Weather</p>
          {data ? (
            <div className="flex items-center gap-4">
              <span className="text-forest">
                <WeatherIcon w={w} size={40} />
              </span>
              <div>
                <p className="type-display-md tabular-nums">
                  {w?.high_f != null ? `${w.high_f}°` : '—'}
                  <span className="type-body-lg ml-1">{w?.low_f != null ? `/ ${w.low_f}°F` : ''}</span>
                </p>
                <p className="type-body-md capitalize">
                  {w?.summary ?? 'No forecast'}
                  {w?.precip_pct != null ? ` · ${w.precip_pct}% rain` : ''} · {data.city}
                </p>
              </div>
            </div>
          ) : (
            <div className="h-12 animate-pulse rounded-2xl bg-white/60" />
          )}
          {data?.weather_note && <p className="type-body-sm">{data.weather_note}</p>}
          <div>
            <LocationChip location={geo.location} status={geo.status} onLocate={geo.locate} onClear={geo.clear} dark={false} />
          </div>
        </GlassPanel>

        {/* Occasion */}
        <GlassPanel radius="hero" className="flex flex-col gap-3 p-5">
          <div className="flex items-center justify-between gap-2">
            <p className="type-micro">Dressing for</p>
            {data && (
              <span className="flex items-center gap-1 text-[12px] font-semibold text-muted">
                <IoCalendarOutline size={13} /> {data.calendar.label}
              </span>
            )}
          </div>
          {data ? (
            <>
              <div className="flex flex-wrap gap-2">
                {data.events.map((e) => (
                  <OccasionButton key={e.id} active={occasionId === e.id} onClick={() => pickOccasion(e.id)} disabled={loading}>
                    <span className="font-bold">{e.name}</span>
                    <span className="opacity-70">
                      {time12(e.start_time)}
                      {e.dress_code_hint ? ` · ${e.dress_code_hint}` : ''}
                    </span>
                  </OccasionButton>
                ))}
                <OccasionButton active={occasionId === EVERYDAY} onClick={() => pickOccasion(EVERYDAY)} disabled={loading}>
                  <span className="font-bold">Everyday</span>
                  <span className="opacity-70">no occasion</span>
                </OccasionButton>
              </div>
              {data.events.length === 0 && data.calendar.source !== 'none' && (
                <p className="type-body-sm">Nothing on your calendar today, so these are everyday looks.</p>
              )}
              {data.calendar.note && <p className="type-body-sm">{data.calendar.note}</p>}
              {data.calendar.source === 'none' && google?.configured && !google.connected && (
                <div className="flex flex-wrap items-center gap-3">
                  <p className="type-body-sm">Connect Google Calendar to dress for today’s events.</p>
                  <button
                    type="button"
                    onClick={connect}
                    className="flex items-center gap-1.5 rounded-full bg-forest px-4 py-2 text-[13px] font-bold text-white hover:opacity-90"
                  >
                    <IoCalendarOutline size={15} /> Connect Google Calendar
                  </button>
                </div>
              )}
              {data.calendar.source === 'none' && !google?.configured && (
                <p className="type-body-sm">No calendar connected, so these are everyday looks.</p>
              )}
            </>
          ) : (
            <div className="h-12 animate-pulse rounded-2xl bg-white/60" />
          )}
        </GlassPanel>
      </div>

      <div className="mb-4 mt-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="type-display-md">{data?.occasion ? `For ${data.occasion.name}` : 'Your everyday options'}</h2>
          {data?.scored_by && (
            <p className="type-body-sm mt-0.5">
              {data.candidates_scored} combinations scored by {data.scored_by}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => load({ eventId: occasionId, exclude: seen, refresh: true })}
            disabled={loading || !data}
            className="flex items-center gap-1.5 rounded-full bg-white/80 px-4 py-2 text-[13px] font-semibold text-ink ring-1 ring-line hover:bg-white disabled:opacity-50"
          >
            <IoRefreshOutline size={15} /> Re-score
          </button>
          <button
            type="button"
            onClick={showDifferent}
            disabled={loading || !data?.outfits.length}
            className="flex items-center gap-1.5 rounded-full bg-forest px-4 py-2 text-[13px] font-bold text-white hover:opacity-90 disabled:opacity-50"
          >
            <IoShuffleOutline size={15} /> Show me others
          </button>
        </div>
      </div>

      {error && (
        <GlassPanel radius="hero" className="mb-4 p-5">
          <p className="type-display-sm">Couldn’t build today’s outfits.</p>
          <p className="type-body-md mt-1">{error}</p>
        </GlassPanel>
      )}

      {loading ? (
        <div className="flex justify-center py-3" aria-busy="true">
          <div className="glass w-[min(calc(100vw-112px),440px)] rounded-hero p-5">
            <div className="h-3 w-16 animate-pulse rounded bg-white/70" />
            <div className="mt-2 h-5 w-48 animate-pulse rounded bg-white/70" />
            <div className="mt-4 grid grid-cols-4 gap-2">
              {[0, 1, 2, 3].map((k) => (
                <div key={k} className="aspect-[5/6] animate-pulse rounded-card bg-white/60" />
              ))}
            </div>
            <div className="mt-6 h-10 animate-pulse rounded-full bg-white/60" />
          </div>
          <p className="sr-only">Building today’s outfits…</p>
        </div>
      ) : data && data.outfits.length === 0 ? (
        <GlassPanel radius="hero" className="p-6">
          <p className="type-display-sm">{seen.length ? 'That’s every combination for today.' : 'No outfits could be built.'}</p>
          <p className="type-body-md mt-1">
            {seen.length ? 'You’ve seen all the good options. Switch the occasion or re-score to start over.' : data.error ?? 'Add a few more pieces to your closet.'}
          </p>
        </GlassPanel>
      ) : (
        <>
          {data && data.outfits.length < 5 && (
            <p className="type-body-sm mb-1 text-center">
              Only {data.outfits.length} truly different look{data.outfits.length === 1 ? '' : 's'} from your closet fit today, so no repeats.
            </p>
          )}
          <SwipeDeck key={data?.outfits.map((o) => o.item_ids.join()).join("|")} label="Today’s outfit options">
          {data?.outfits.map((o, n) => (
            <DailyOutfitCard
              key={o.ref}
              n={n + 1}
              outfit={o}
              items={items}
              worn={sameSet(worn, o.item_ids)}
              busy={wearing === o.ref}
              onWear={() => wear(o)}
            />
          ))}
          </SwipeDeck>
        </>
      )}
      {toast}
    </PageShell>
  );
}

function OccasionButton({
  active,
  onClick,
  disabled,
  children,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`flex flex-col items-start rounded-2xl px-3.5 py-2 text-left text-[12px] leading-4 transition disabled:cursor-wait ${
        active ? 'bg-forest text-white' : 'bg-white/75 text-ink ring-1 ring-line hover:bg-white'
      }`}
    >
      {children}
    </button>
  );
}

function DailyOutfitCard({
  n,
  outfit,
  items,
  worn,
  busy,
  onWear,
}: {
  n: number;
  outfit: DailyOutfit;
  items: Map<string, WardrobeItem>;
  worn: boolean;
  busy: boolean;
  onWear: () => void;
}) {
  const [showWhy, setShowWhy] = useState(false);
  return (
    <article className={`glass flex w-full flex-col overflow-hidden rounded-hero ring-2 transition ${worn ? 'ring-emerald' : 'ring-transparent'}`}>
      <header className="flex items-start justify-between gap-3 px-5 pt-5">
        <div>
          <p className="type-micro mb-1">Option {n}</p>
          <h3 className="type-display-sm">{outfit.title}</h3>
        </div>
        <ScorePill value={outfit.scores.overall} />
      </header>

      <div className={`grid gap-2 px-5 pt-4 ${outfit.item_ids.length >= 5 ? 'grid-cols-5' : outfit.item_ids.length === 4 ? 'grid-cols-4' : 'grid-cols-3'}`}>
        {outfit.item_ids.map((id) => {
          const it = items.get(id);
          return (
            <figure key={id} className="overflow-hidden rounded-card bg-white/80">
              <div className="aspect-[5/6] bg-sand-100">
                {it && <img src={it.image_url} alt={it.name} draggable={false} className="h-full w-full object-cover" />}
              </div>
              <figcaption className="truncate px-2 py-1.5 text-[11px] font-semibold leading-4 text-ink" title={it?.name}>
                {it?.name ?? 'Item'}
              </figcaption>
            </figure>
          );
        })}
      </div>

      <div className="flex flex-1 flex-col px-5 pb-5 pt-4">
        <p className="type-body-md text-ink/80">{outfit.tip}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowWhy(!showWhy)}
            className="flex items-center gap-1 rounded-full bg-white/80 px-3 py-1.5 text-[12px] font-semibold text-ink ring-1 ring-line hover:bg-white"
          >
            Score breakdown <IoChevronDown className={`transition-transform ${showWhy ? 'rotate-180' : ''}`} />
          </button>
          {n === 1 && <MicroChip tone="green">Top pick</MicroChip>}
        </div>
        {showWhy && (
          <div className="mt-3 rounded-2xl bg-white/75 p-4">
            <p className="type-body-sm mb-3">{outfit.rationale}</p>
            <ScoreBreakdown scores={outfit.scores} compact />
          </div>
        )}
        <div className="mt-auto pt-4">
          {worn ? (
            <p className="flex items-center justify-center gap-1.5 rounded-full bg-[rgba(52,211,153,0.18)] py-2.5 text-[14px] font-bold text-forest">
              <IoCheckmarkCircle size={18} /> Wearing this today
            </p>
          ) : (
            <button
              type="button"
              onClick={onWear}
              disabled={busy}
              className="w-full rounded-full bg-forest py-2.5 text-[14px] font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Wear this'}
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

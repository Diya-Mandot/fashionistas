import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  IoBarbellOutline,
  IoBriefcaseOutline,
  IoCalendarOutline,
  IoCheckmarkCircle,
  IoChevronDown,
  IoHeartOutline,
  IoCloudOutline,
  IoRainyOutline,
  IoRefreshOutline,
  IoShirtOutline,
  IoShuffleOutline,
  IoSparklesOutline,
  IoSnowOutline,
  IoSunnyOutline,
  IoWineOutline,
} from 'react-icons/io5';
import { MicroChip } from '../components/Chip';
import { GlassPanel } from '../components/GlassPanel';
import { LocationChip } from '../components/LocationChip';
import { PageShell } from '../components/PageShell';
import { ScoreBreakdown, ScorePill } from '../components/ScoreBreakdown';
import { SwipeDeck } from '../components/SwipeDeck';
import { useToast } from '../components/Toast';
import { api } from '../lib/api';
import type { DailyOutfit, DailyResponse, DailyWeather, WardrobeItem } from '../lib/types';
import { useDeviceLocation } from '../lib/useDeviceLocation';

const EVERYDAY = 'everyday';

const PRESET_ICONS: Record<string, ReactNode> = {
  'preset:work': <IoBriefcaseOutline size={16} />,
  'preset:gym': <IoBarbellOutline size={16} />,
  'preset:date-night': <IoHeartOutline size={16} />,
  'preset:going-out': <IoWineOutline size={16} />,
};

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

  const dateLabel = new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
  const w = data?.weather ?? null;
  const weatherTitle = data
    ? [
        w?.summary ?? 'No forecast',
        w?.high_f != null ? `High ${w.high_f}°F` : null,
        w?.low_f != null ? `Low ${w.low_f}°F` : null,
        w?.precip_pct != null ? `${w.precip_pct}% rain` : null,
        data.city,
        data.weather_note,
      ]
        .filter(Boolean)
        .join(' · ')
    : 'Loading weather';

  return (
    <PageShell>
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="type-micro mb-2">{dateLabel}</p>
          <h1 className="type-display-lg">Today’s outfit</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Weather, compact: details on hover / long-press via the title. */}
          <span
            title={weatherTitle}
            aria-label={weatherTitle}
            className="flex items-center gap-1.5 rounded-full bg-white/80 px-3 py-1.5 text-[13px] font-bold text-ink ring-1 ring-line"
          >
            <span className="text-forest">
              <WeatherIcon w={w} size={18} />
            </span>
            <span className="tabular-nums">{w?.high_f != null ? `${w.high_f}°` : data ? '—' : '…'}</span>
          </span>
          <LocationChip location={geo.location} status={geo.status} onLocate={geo.locate} onClear={geo.clear} dark={false} />
        </div>
      </header>

      {/* Occasion filter: everyday and presets always, then today's calendar events. Scrolls sideways on phones. */}
      <div className="no-scrollbar -mx-1 mb-6 overflow-x-auto px-1 py-1">
        <div role="group" aria-label="Dress for" className="flex w-max gap-2">
          <OccasionButton
            icon={<IoShirtOutline size={16} />}
            active={occasionId === EVERYDAY}
            onClick={() => pickOccasion(EVERYDAY)}
            disabled={loading || !data}
          >
            Everyday
          </OccasionButton>
          {data?.presets.map((p) => (
            <OccasionButton
              key={p.id}
              icon={PRESET_ICONS[p.id] ?? <IoSparklesOutline size={16} />}
              active={occasionId === p.id}
              onClick={() => pickOccasion(p.id)}
              disabled={loading}
            >
              {p.name}
            </OccasionButton>
          ))}
          {data?.events.map((e) => (
            <OccasionButton
              key={e.id}
              icon={<IoCalendarOutline size={16} />}
              active={occasionId === e.id}
              onClick={() => pickOccasion(e.id)}
              disabled={loading}
              detail={time12(e.start_time)}
            >
              {e.name}
            </OccasionButton>
          ))}
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h2 className="type-display-md">{data?.occasion ? `${data.occasion.name} looks` : 'Your everyday options'}</h2>
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
        <div className="flex py-3" aria-busy="true">
          <div className="glass w-[min(calc(100vw-72px),440px)] rounded-hero p-5">
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
            <p className="type-body-sm mb-1">
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
  icon,
  active,
  onClick,
  disabled,
  detail,
  children,
}: {
  icon: ReactNode;
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  detail?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full py-2 pl-3 pr-4 text-[13px] font-semibold transition-all duration-200 disabled:cursor-wait focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald/60 ${
        active
          ? 'bg-forest text-white shadow-[0_6px_18px_-6px_rgba(26,50,38,0.55)]'
          : 'bg-white/70 text-ink/80 ring-1 ring-white/70 backdrop-blur-md hover:-translate-y-px hover:bg-white hover:text-ink hover:shadow-sm'
      }`}
    >
      <span
        aria-hidden="true"
        className={`flex h-6 w-6 items-center justify-center rounded-full ${active ? 'bg-white/15' : 'bg-sage-100 text-forest'}`}
      >
        {icon}
      </span>
      {children}
      {detail && <span className={`text-[12px] font-medium ${active ? 'text-white/70' : 'text-muted'}`}>{detail}</span>}
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

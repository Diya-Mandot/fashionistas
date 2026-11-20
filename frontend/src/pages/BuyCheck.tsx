import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import {
  IoBagCheckOutline,
  IoBookmarkOutline,
  IoCalendarOutline,
  IoCheckmarkCircle,
  IoCopyOutline,
  IoExtensionPuzzleOutline,
  IoRefreshOutline,
  IoSearchOutline,
} from 'react-icons/io5';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { MicroChip } from '../components/Chip';
import { GarmentCamera } from '../components/GarmentCamera';
import { GlassPanel } from '../components/GlassPanel';
import { PageShell } from '../components/PageShell';
import { PhotoDrop, previewUrl } from '../components/PhotoDrop';
import { StepList, useStepReveal } from '../components/StepList';
import { useToast } from '../components/Toast';
import { VerdictBadge, verdictLabel } from '../components/VerdictBadge';
import { api, PaywallError } from '../lib/api';
import type { BuyCheckResponse, BuyCheckResult, Paywall, TraceStep, WardrobeItem } from '../lib/types';

const PENDING_STEPS = [
  'Checking photo…',
  'Google Vision is looking at it…',
  'Claude is reading the item…',
  'Matching it against your closet…',
  'Claude is weighing the verdict…',
];
const NEW_ITEM_ID = 'new';
const OUTFIT_CAP = 50;
const WISHLIST_KEY = 'fashionistas:wishlist';

type Phase = 'idle' | 'working' | 'done' | 'error' | 'paywall';

export function BuyCheck({ active = true }: { active?: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [phase, setPhase] = useState<Phase>('idle');
  const [preview, setPreview] = useState<string | null>(null);
  const [res, setRes] = useState<BuyCheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paywall, setPaywall] = useState<Paywall | null>(null);
  const [kept, setKept] = useState<WardrobeItem | null>(null);
  const { toast, show: setToast } = useToast();
  const trace: TraceStep[] = res?.trace ?? [];
  const { shown, allShown, pending } = useStepReveal(trace, phase === 'working', PENDING_STEPS);

  // /buy?check=chk_… reopens a past result (also the demo's safety net).
  // Runs only when the URL changes, so clearing the result ("Check another")
  // can't race the URL update and reload the old check.
  const urlCheck = new URLSearchParams(location.search).get('check');
  const currentId = useRef<string | null>(null);
  currentId.current = res?.check_id ?? null;
  useEffect(() => {
    if (!active || !urlCheck || currentId.current === urlCheck) return;
    api
      .getBuyCheck(urlCheck)
      .then((r) => {
        setRes(r);
        setPreview(null);
        setKept(null);
        setPhase('done');
      })
      .catch(() => {
        setError('That check could not be found.');
        setPhase('error');
      });
  }, [active, urlCheck]);

  // Bumped on every start/reset so a check that finishes after Back is ignored.
  const attempt = useRef(0);

  const start = useCallback(
    async (file: File) => {
      const mine = ++attempt.current;
      setPhase('working');
      setError(null);
      setPaywall(null);
      setRes(null);
      setKept(null);
      setPreview(previewUrl(file));
      try {
        const r = await api.buyCheck(file);
        if (mine !== attempt.current) return;
        setRes(r);
        setPhase('done');
        navigate(`/buy?check=${r.check_id}`, { replace: true });
      } catch (e) {
        if (mine !== attempt.current) return;
        if (e instanceof PaywallError) {
          setPaywall(e.paywall);
          setPhase('paywall');
        } else {
          setError(e instanceof Error ? e.message : String(e));
          setPhase('error');
        }
      }
    },
    [navigate],
  );

  const reset = () => {
    attempt.current++;
    setPhase('idle');
    setRes(null);
    setPreview(null);
    setKept(null);
    setError(null);
    navigate('/buy', { replace: true });
  };

  const keep = async () => {
    if (!res) return;
    try {
      const { item } = await api.keepBuyCheck(res.check_id);
      setKept(item);
      setRes(withImage(res, item.image_url)); // the photo moved out of pending/
      setToast(`Added ${item.name} to your closet`);
    } catch (e) {
      setToast(e instanceof Error ? e.message : 'Could not add it to your closet');
    }
  };

  const saveForLater = () => {
    if (!res) return;
    saveToWishlist(res);
    setToast('Saved for later on this device');
  };

  const showResult = phase === 'done' && !!res && (allShown || trace.length === 0);

  // Past the upload screen, Back returns to it; on the upload screen it leaves the page.
  const onUploadScreen = phase === 'idle' && !urlCheck;

  return (
    <PageShell onBack={onUploadScreen ? undefined : reset}>
      <div className="mb-8">
        <p className="type-micro mb-2">Before you buy</p>
        <h1 className="type-display-lg">Should I buy this?</h1>
        <p className="type-body-md mt-1 max-w-[600px]">
          Snap the piece in the store or screenshot it online. We count the outfits it unlocks with what you
          already own, flag anything it duplicates, and tell you if it is worth it.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
        {/* Left: photo, then the trace once the result is up */}
        <div className="flex min-w-0 flex-col gap-4">
          <GlassPanel radius="hero" className="p-4">
            {phase === 'idle' || phase === 'error' || phase === 'paywall' ? (
              // Only mounted while this tab is showing, so a hidden tab never holds the webcam.
              active && (
                <GarmentCamera
                  onScan={start}
                  captureLabel="Take photo and check"
                  hint="Hold the item in frame. Keep its color and shape visible."
                >
                  <PhotoDrop onFile={start} error={phase === 'error' ? error : null} label="Or drop a photo or screenshot" />
                </GarmentCamera>
              )
            ) : (
              <div className="relative aspect-[4/3] overflow-hidden rounded-card bg-sand-100 lg:aspect-[5/6]">
                {(preview || res?.item.image_url) && (
                  <img src={preview ?? res?.item.image_url ?? ''} alt="Item being checked" className="h-full w-full object-cover" />
                )}
                {phase === 'working' && (
                  <div className="absolute inset-x-0 top-0 h-1 overflow-hidden bg-white/40">
                    <div className="h-full w-1/3 animate-[scan_1.2s_ease-in-out_infinite] bg-emerald" />
                  </div>
                )}
              </div>
            )}
          </GlassPanel>
          {showResult && <HowWeDecided trace={trace} shown={shown} pending={pending} className="hidden lg:block" />}
        </div>

        {/* Right: progress, then the verdict */}
        <div className="flex min-w-0 flex-col gap-4">
          {phase === 'paywall' && paywall && <PaywallNotice paywall={paywall} onOverride={reset} />}
          {phase === 'idle' && !urlCheck && (
            <GlassPanel radius="hero" className="p-5">
              <p className="type-micro mb-3">What you get</p>
              <ul className="type-body-md flex flex-col gap-2">
                <li>• How many new outfits it unlocks with your closet</li>
                <li>• Pieces you already own that it duplicates</li>
                <li>• The gap it fills and the events it works for</li>
                <li>• Cost per wear, if you add the price</li>
              </ul>
            </GlassPanel>
          )}
          {(phase === 'working' || (phase === 'done' && !showResult)) && (
            <GlassPanel radius="hero" className="p-5">
              <p className="type-micro mb-4">Checking</p>
              <StepList trace={trace} shown={shown} pending={pending} />
            </GlassPanel>
          )}
          {showResult && res && (
            <ResultPanel
              res={res}
              kept={kept}
              onKeep={keep}
              onSave={saveForLater}
              onAnother={reset}
            />
          )}
          {/* On phones the verdict comes first; the trace follows it. */}
          {showResult && <HowWeDecided trace={trace} shown={shown} pending={pending} className="lg:hidden" />}
        </div>
      </div>

      {toast}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------
function ResultPanel({
  res,
  kept,
  onKeep,
  onSave,
  onAnother,
}: {
  res: BuyCheckResponse;
  kept: WardrobeItem | null;
  onKeep: () => void;
  onSave: () => void;
  onAnother: () => void;
}) {
  const { item, result: r, usage } = res;
  const count = r.outfit_count > OUTFIT_CAP ? `${OUTFIT_CAP}+` : String(r.outfit_count);
  return (
    <GlassPanel radius="hero" className="animate-[fadeUp_.35s_ease-out] p-5 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <VerdictBadge verdict={r.verdict} score={r.score} />
        {!usage.pro && (
          <span className="text-[12px] text-muted">
            {usage.checks_used} of {usage.limit} free checks used
          </span>
        )}
      </div>

      <h2 className="type-display-md mt-5">
        {r.outfit_count > 0 ? `Unlocks ${count} new outfit${r.outfit_count === 1 ? '' : 's'}` : 'Pairs with nothing you own yet'}
      </h2>
      <p className="type-body-md mt-1">
        {item.name} · <span className="capitalize">{item.formality}</span>
        {item.season ? ` · ${item.season}` : ''}
      </p>
      <p className="type-body-lg mt-3 text-ink/85">{r.score_reason}</p>

      <ul className="mt-5 flex flex-col gap-3">
        {r.duplicates.length > 0 && (
          <Fact icon={<IoCopyOutline size={18} />} tone="warn">
            You own {r.duplicates.length} similar piece{r.duplicates.length === 1 ? '' : 's'}:{' '}
            {r.duplicates.map((d, i) => (
              <span key={d.item_id}>
                {i > 0 && ', '}
                <Link to={`/closet?item=${d.item_id}`} className="font-semibold text-ocean-deep underline-offset-2 hover:underline">
                  {d.name}
                </Link>
              </span>
            ))}
          </Fact>
        )}
        {r.gap_filled && (
          <Fact icon={<IoExtensionPuzzleOutline size={18} />} tone="good">
            Fills: <span className="font-semibold text-ink">{r.gap_filled}</span>
          </Fact>
        )}
        {r.calendar_matches.length > 0 && (
          <Fact icon={<IoCalendarOutline size={18} />} tone="good">
            {calendarLine(r.calendar_matches)}
          </Fact>
        )}
      </ul>

      <CostPerWear result={r} />

      {r.top_outfits.length > 0 && (
        <div className="mt-6">
          <p className="type-micro mb-3">Wear it with what you own</p>
          <div className="flex flex-col gap-3">
            {r.top_outfits.map((o, n) => (
              <OutfitPreview key={n} items={o.items} />
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-2">
        {kept ? (
          <Link
            to={`/closet?item=${kept.id}`}
            className="flex items-center gap-1.5 rounded-full bg-sage-100 px-4 py-2 text-[13px] font-bold text-forest-mid"
          >
            <IoCheckmarkCircle size={16} /> In your closet →
          </Link>
        ) : (
          <button
            type="button"
            onClick={onKeep}
            className="flex items-center gap-1.5 rounded-full bg-forest px-4 py-2 text-[13px] font-bold text-white hover:opacity-90"
          >
            <IoBagCheckOutline size={16} /> I bought it
          </button>
        )}
        <button
          type="button"
          onClick={onSave}
          className="flex items-center gap-1.5 rounded-full border border-line bg-white px-4 py-2 text-[13px] font-semibold text-ink hover:bg-sand-50"
        >
          <IoBookmarkOutline size={15} /> Save for later
        </button>
        <Link
          to={`/shop?category=${encodeURIComponent(item.category)}&from=buy`}
          className="flex items-center gap-1.5 rounded-full border border-line bg-white px-4 py-2 text-[13px] font-semibold text-ink hover:bg-sand-50"
        >
          <IoSearchOutline size={15} /> Find something better
        </Link>
        <button type="button" onClick={onAnother} className="flex items-center gap-1 px-2 text-[13px] font-semibold text-ocean-deep">
          <IoRefreshOutline size={14} /> Check another
        </button>
      </div>
    </GlassPanel>
  );
}

function HowWeDecided({
  trace,
  shown,
  pending,
  className,
}: {
  trace: TraceStep[];
  shown: number;
  pending: string | null;
  className: string;
}) {
  return (
    <GlassPanel radius="hero" className={`p-5 ${className}`}>
      <p className="type-micro mb-4">How we decided</p>
      <StepList trace={trace} shown={shown} pending={pending} />
    </GlassPanel>
  );
}

function Fact({ icon, tone, children }: { icon: ReactNode; tone: 'good' | 'warn'; children: ReactNode }) {
  return (
    <li className="flex items-start gap-3 rounded-2xl bg-white/70 p-3">
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          tone === 'good' ? 'bg-sage-100 text-forest-mid' : 'bg-accent-light text-[#8A6236]'
        }`}
      >
        {icon}
      </span>
      <span className="type-body-md pt-1.5">{children}</span>
    </li>
  );
}

function CostPerWear({ result }: { result: BuyCheckResult }) {
  const [price, setPrice] = useState('');
  const value = Number.parseFloat(price);
  const wears = result.est_wears_per_year;
  return (
    <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl bg-white/70 p-3">
      <label className="type-body-sm flex items-center gap-2">
        Price
        <span className="flex items-center rounded-xl border border-line bg-white px-2 focus-within:ring-2 focus-within:ring-emerald/50">
          <span className="text-muted">$</span>
          <input
            inputMode="decimal"
            value={price}
            onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ''))}
            placeholder="49"
            aria-label="Price in dollars"
            className="w-20 bg-transparent px-1 py-1.5 text-[14px] text-ink focus:outline-none"
          />
        </span>
      </label>
      <span className="type-body-md">
        {value > 0 ? (
          <>
            ${fmtMoney(value)} / about {wears} wears ={' '}
            <span className="font-bold text-ink">${fmtMoney(value / wears)} per wear</span>
          </>
        ) : (
          `You'd wear it about ${wears} times a year`
        )}
      </span>
    </div>
  );
}

function OutfitPreview({ items }: { items: WardrobeItem[] }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {items.map((it) => {
        const isNew = it.id === NEW_ITEM_ID;
        return (
          <figure
            key={it.id}
            className={`relative overflow-hidden rounded-card bg-white/80 ${isNew ? 'ring-2 ring-emerald' : ''}`}
          >
            <div className="aspect-[5/6] bg-sand-100">
              {it.image_url && <img src={it.image_url} alt={it.name} className="h-full w-full object-cover" />}
            </div>
            {isNew && (
              <span className="absolute left-1.5 top-1.5">
                <MicroChip tone="green">New</MicroChip>
              </span>
            )}
            <figcaption className="line-clamp-2 px-2 py-1.5 text-[11px] font-semibold leading-4 text-ink">{it.name}</figcaption>
          </figure>
        );
      })}
    </div>
  );
}

function PaywallNotice({ paywall, onOverride }: { paywall: Paywall; onOverride: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Testing only: gives back the free checks; the limit kicks in again after the next few.
  const override = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.resetBuyChecks();
      onOverride();
    } catch {
      setErr('Override failed. Are dev endpoints on (DEV_ENDPOINTS)?');
    } finally {
      setBusy(false);
    }
  };
  return (
    <GlassPanel radius="hero" className="p-5">
      <p className="type-micro mb-2">Free plan</p>
      <h2 className="type-display-sm">You've used your {paywall.limit} free checks this month.</h2>
      <p className="type-body-md mt-2">Pro gives you unlimited checks. Upgrades are coming soon.</p>
      {import.meta.env.DEV && (
        <div className="mt-4 border-t border-dashed border-line pt-3">
          <button
            type="button"
            onClick={override}
            disabled={busy}
            className="rounded-full border border-dashed border-ink/40 px-3.5 py-1.5 text-[12px] font-semibold text-ink hover:bg-white disabled:opacity-50"
          >
            {busy ? 'Resetting…' : `Dev: reset ${paywall.limit} free checks`}
          </button>
          {err && <p className="mt-2 text-[12px] text-muted">{err}</p>}
        </div>
      )}
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function withImage(res: BuyCheckResponse, imageUrl: string): BuyCheckResponse {
  return {
    ...res,
    item: { ...res.item, image_url: imageUrl },
    result: {
      ...res.result,
      top_outfits: res.result.top_outfits.map((o) => ({
        ...o,
        items: o.items.map((it) => (it.id === NEW_ITEM_ID ? { ...it, image_url: imageUrl } : it)),
      })),
    },
  };
}

function fmtMoney(n: number): string {
  return n.toFixed(2).replace(/\.00$/, '');
}

function calendarLine(matches: BuyCheckResult['calendar_matches']): string {
  const first = matches[0];
  const d = new Date(`${first.date}T12:00:00`);
  const days = Math.round((d.getTime() - Date.now()) / 86_400_000);
  const when = days < 7 ? d.toLocaleDateString(undefined, { weekday: 'long' }) : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const n = matches.length;
  return n === 1
    ? `Works for ${when}'s ${first.event}`
    : `Works for ${n} events in the next month, including ${when}'s ${first.event}`;
}

/** Save for later lives on this device only (wishlist persistence is out of scope). */
function saveToWishlist(res: BuyCheckResponse) {
  try {
    const list = JSON.parse(localStorage.getItem(WISHLIST_KEY) ?? '[]') as { check_id: string }[];
    const entry = {
      check_id: res.check_id,
      name: res.item.name,
      image_url: res.item.image_url,
      verdict: verdictLabel(res.result.verdict),
      score: res.result.score,
      saved_at: new Date().toISOString(),
    };
    localStorage.setItem(WISHLIST_KEY, JSON.stringify([entry, ...list.filter((e) => e.check_id !== res.check_id)].slice(0, 50)));
  } catch {
    // storage blocked (private mode): nothing to persist
  }
}

import { useCallback, useEffect, useState } from 'react';
import { IoArrowUndoOutline, IoCreateOutline, IoHelpCircleOutline, IoRefreshOutline, IoShirtOutline } from 'react-icons/io5';
import { Link } from 'react-router-dom';
import { MicroChip } from '../components/Chip';
import { GarmentCamera } from '../components/GarmentCamera';
import { GlassPanel } from '../components/GlassPanel';
import { PageShell } from '../components/PageShell';
import { PhotoDrop, previewUrl } from '../components/PhotoDrop';
import { StepList, useStepReveal } from '../components/StepList';
import { useToast } from '../components/Toast';
import { api } from '../lib/api';
import type { TraceStep, WardrobeItem } from '../lib/types';

const UNDO_SECONDS = 10;
const PENDING_STEPS = ['Checking photo…', 'Google Vision is looking at it…', 'Claude is classifying…', 'Saving to closet…'];

type Phase = 'idle' | 'working' | 'done' | 'undone' | 'error';

export function Scan({ active = true, onClosetChange }: { active?: boolean; onClosetChange: (scanId: string | null) => void }) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [preview, setPreview] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [item, setItem] = useState<WardrobeItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(UNDO_SECONDS);
  const [editing, setEditing] = useState(false);
  const { shown, allShown: traceShown, pending } = useStepReveal(trace, phase === 'working', PENDING_STEPS);
  const allShown = traceShown && phase === 'done';
  const { toast, show: showToast } = useToast();

  // Daily outfit log: placeholder until the backend can pick out each worn piece.
  const logOutfit = (file: File) => {
    showToast(`Outfit photo received (${file.name}). Daily logging is coming soon.`);
  };

  useEffect(() => {
    if (preview) return () => URL.revokeObjectURL(preview);
  }, [preview]);

  // Undo window.
  useEffect(() => {
    if (phase !== 'done' || editing || !allShown) return;
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [phase, countdown, editing, allShown]);

  const start = useCallback(async (file: File) => {
    setPhase('working');
    setError(null);
    setTrace([]);
    setItem(null);
    setEditing(false);
    setCountdown(UNDO_SECONDS);
    setPreview(previewUrl(file));
    try {
      const res = await api.scan(file);
      setTrace(res.trace);
      setItem(res.item);
      setPhase('done');
      onClosetChange(res.item.id);
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^\d+ /, '') : String(e));
      setPhase('error');
    }
  }, [onClosetChange]);

  const undo = async () => {
    if (!item) return;
    await api.deleteItem(item.id);
    setPhase('undone');
    onClosetChange(null);
  };

  const saveEdit = async (patch: Partial<WardrobeItem>) => {
    if (!item) return;
    setItem(await api.updateItem(item.id, patch));
    setEditing(false);
    onClosetChange(item.id);
  };

  const reset = () => {
    setPhase('idle');
    setTrace([]);
    setItem(null);
    setPreview(null);
  };

  return (
    <PageShell>
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="type-micro mb-2">Agentic closet scan</p>
          <h1 className="type-display-lg">Digital closet</h1>
          <p className="type-body-md mt-1 max-w-[560px]">
            Take or upload a garment photo. The scan identifies the item and saves it to your closet.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 self-start md:self-auto">
          <label className="flex cursor-pointer items-center gap-1.5 rounded-full border border-forest bg-forest px-4 py-2 text-[13px] font-bold text-white transition-colors hover:bg-forest/90 focus-within:ring-2 focus-within:ring-emerald">
            <IoShirtOutline size={16} /> Log today&apos;s outfit
            <input
              type="file"
              accept="image/*"
              capture="user"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) logOutfit(f);
              }}
            />
          </label>
          <Link
            to="/buy"
            className="flex items-center gap-1.5 rounded-full border border-forest bg-white/80 px-4 py-2 text-[13px] font-bold text-forest hover:bg-white"
          >
            <IoHelpCircleOutline size={16} /> Should I buy this?
          </Link>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* Left: upload / preview */}
        <GlassPanel radius="hero" className="p-4">
          {phase === 'idle' || phase === 'error' ? active && (
            <GarmentCamera onScan={start}>
              <PhotoDrop onFile={start} error={error} />
            </GarmentCamera>
          ) : (
            <div className="relative aspect-[4/3] overflow-hidden rounded-card bg-sand-100 lg:aspect-[5/6]">
              {(item?.image_url || preview) && (
                <img src={item?.image_url ?? preview ?? ''} alt="Uploaded item" className="h-full w-full object-cover" />
              )}
              {phase === 'working' && (
                <div className="absolute inset-x-0 top-0 h-1 overflow-hidden bg-white/40">
                  <div className="h-full w-1/3 animate-[scan_1.2s_ease-in-out_infinite] bg-emerald" />
                </div>
              )}
            </div>
          )}
        </GlassPanel>

        {/* Right: trace + result */}
        <div className="flex flex-col gap-4">
          <GlassPanel radius="hero" className="p-5">
            <p className="type-micro mb-4">Agent trace</p>
            {phase === 'idle' && (
              <p className="type-body-md">Steps will appear here as the scan runs: Vision → Claude → saved.</p>
            )}
            <StepList trace={trace} shown={shown} pending={pending} />
          </GlassPanel>
          {allShown && item && (
            <GlassPanel radius="hero" className="animate-[fadeUp_.35s_ease-out] p-5">
              {editing ? (
                <EditForm item={item} onSave={saveEdit} onCancel={() => setEditing(false)} />
              ) : (
                <>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="type-micro mb-1 text-forest-mid" role="status">Saved to closet</p>
                      <h2 className="type-display-sm">{item.name}</h2>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <MicroChip>{item.category}</MicroChip>
                        <MicroChip tone="green">{item.formality}</MicroChip>
                        {item.season && <MicroChip tone="sand">{item.season}</MicroChip>}
                        {item.material && <MicroChip>{item.material}</MicroChip>}
                        <MicroChip tone="ocean">{item.waterproof ? 'Waterproof' : 'Not waterproof'}</MicroChip>
                      </div>
                    </div>
                  </div>
                  <div className="mt-5 flex flex-wrap items-center gap-2">
                    {countdown > 0 && (
                      <>
                        <button
                          type="button"
                          onClick={undo}
                          className="flex items-center gap-1.5 rounded-full border border-line bg-white px-4 py-2 text-[13px] font-semibold text-ink hover:bg-sand-50"
                        >
                          <IoArrowUndoOutline size={15} /> Undo ({countdown}s)
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditing(true)}
                          className="flex items-center gap-1.5 rounded-full border border-line bg-white px-4 py-2 text-[13px] font-semibold text-ink hover:bg-sand-50"
                        >
                          <IoCreateOutline size={15} /> Edit
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={reset}
                      className="flex items-center gap-1.5 rounded-full bg-forest px-4 py-2 text-[13px] font-bold text-white hover:opacity-90"
                    >
                      <IoRefreshOutline size={15} /> Scan another
                    </button>
                    <Link to="/closet" className="px-2 text-[13px] font-semibold text-ocean-deep">
                      View closet →
                    </Link>
                  </div>
                </>
              )}
            </GlassPanel>
          )}

          {phase === 'undone' && (
            <GlassPanel radius="hero" className="p-5">
              <p className="type-label-bold">Removed. Nothing was saved.</p>
              <button type="button" onClick={reset} className="mt-3 text-[13px] font-semibold text-ocean-deep">
                Scan another →
              </button>
            </GlassPanel>
          )}
        </div>
      </div>
      {toast}
    </PageShell>
  );
}

const CATS = ['tops', 'bottoms', 'dresses', 'outerwear', 'shoes', 'accessories', 'bags', 'activewear'];
const FORMS = ['casual', 'smart casual', 'business', 'formal'];

function EditForm({
  item,
  onSave,
  onCancel,
}: {
  item: WardrobeItem;
  onSave: (p: Partial<WardrobeItem>) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(item.name);
  const [category, setCategory] = useState(item.category);
  const [formality, setFormality] = useState(item.formality);
  const [waterproof, setWaterproof] = useState(item.waterproof);
  const field = 'mt-1 w-full rounded-xl border border-line bg-white px-3 py-2 text-[14px] text-ink focus:outline-none focus:ring-2 focus:ring-emerald/50';
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ name, category, formality, waterproof });
      }}
    >
      <label className="type-body-sm sm:col-span-2">
        Name
        <input className={field} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="type-body-sm">
        Category
        <select className={field} value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATS.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <label className="type-body-sm">
        Formality
        <select className={field} value={formality} onChange={(e) => setFormality(e.target.value)}>
          {FORMS.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <label className="type-body-sm flex items-center gap-2 sm:col-span-2">
        <input type="checkbox" checked={waterproof} onChange={(e) => setWaterproof(e.target.checked)} /> Waterproof
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <button type="submit" className="rounded-full bg-forest px-4 py-2 text-[13px] font-bold text-white">
          Save
        </button>
        <button type="button" onClick={onCancel} className="rounded-full px-4 py-2 text-[13px] font-semibold text-ink">
          Cancel
        </button>
      </div>
    </form>
  );
}

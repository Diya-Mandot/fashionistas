import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react';
import { IoArrowUndoOutline, IoCloudUploadOutline, IoCreateOutline, IoRefreshOutline } from 'react-icons/io5';
import { Link } from 'react-router-dom';
import { MicroChip } from '../components/Chip';
import { GlassPanel } from '../components/GlassPanel';
import { JsonBlock } from '../components/JsonBlock';
import { PageShell } from '../components/PageShell';
import { SourceBadge } from '../components/SourceBadge';
import { StepIcon } from '../components/StepIcon';
import { api } from '../lib/api';
import type { TraceStep, WardrobeItem } from '../lib/types';

const UNDO_SECONDS = 10;
const PENDING_STEPS = ['Checking photo…', 'Google Vision is looking at it…', 'Decisions API is classifying…', 'Saving to closet…'];

type Phase = 'idle' | 'working' | 'done' | 'undone' | 'error';

export function Scan() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [preview, setPreview] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [shown, setShown] = useState(0);
  const [pendingIdx, setPendingIdx] = useState(0);
  const [item, setItem] = useState<WardrobeItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(UNDO_SECONDS);
  const [editing, setEditing] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [openStep, setOpenStep] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Cycle the "in progress" label while the request runs.
  useEffect(() => {
    if (phase !== 'working') return;
    const t = setInterval(() => setPendingIdx((i) => Math.min(i + 1, PENDING_STEPS.length - 1)), 1100);
    return () => clearInterval(t);
  }, [phase]);

  // Reveal returned steps one by one.
  useEffect(() => {
    if (shown >= trace.length) return;
    const t = setTimeout(() => setShown((n) => n + 1), 450);
    return () => clearTimeout(t);
  }, [shown, trace.length]);

  // Undo window.
  useEffect(() => {
    if (phase !== 'done' || editing || shown < trace.length) return;
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [phase, countdown, editing, shown, trace.length]);

  const start = useCallback(async (file: File) => {
    setPhase('working');
    setError(null);
    setTrace([]);
    setShown(0);
    setPendingIdx(0);
    setItem(null);
    setEditing(false);
    setCountdown(UNDO_SECONDS);
    setPreview(file.type.startsWith('image/') && !/heic|heif/i.test(file.type) ? URL.createObjectURL(file) : null);
    try {
      const res = await api.scan(file);
      setTrace(res.trace);
      setItem(res.item);
      setPhase('done');
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^\d+ /, '') : String(e));
      setPhase('error');
    }
  }, []);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) start(f);
  };

  const undo = async () => {
    if (!item) return;
    await api.deleteItem(item.id);
    setPhase('undone');
  };

  const saveEdit = async (patch: Partial<WardrobeItem>) => {
    if (!item) return;
    setItem(await api.updateItem(item.id, patch));
    setEditing(false);
  };

  const reset = () => {
    setPhase('idle');
    setTrace([]);
    setItem(null);
    setPreview(null);
  };

  const allShown = shown >= trace.length && phase === 'done';

  return (
    <PageShell>
      <div className="mb-8">
        <p className="type-micro mb-2">Agentic closet scan</p>
        <h1 className="type-display-lg">Digital closet</h1>
        <p className="type-body-md mt-1 max-w-[560px]">
          Upload a photo of any piece, even a messy one. Google Vision reads it, the Decisions API classifies it,
          and it lands in your closet with zero typing.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* Left: upload / preview */}
        <GlassPanel radius="hero" className="p-4">
          {phase === 'idle' || phase === 'error' ? (
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={`flex aspect-[4/3] cursor-pointer flex-col items-center justify-center gap-3 rounded-card border-2 border-dashed text-center transition-colors lg:aspect-[5/6] ${
                dragOver ? 'border-emerald bg-[rgba(52,211,153,0.10)]' : 'border-sage-200 bg-white/60 hover:bg-white/80'
              }`}
            >
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-forest text-white">
                <IoCloudUploadOutline size={26} />
              </span>
              <span className="type-label-bold">Drop a photo or click to upload</span>
              <span className="type-body-sm">JPG, PNG, WEBP or HEIC · up to 15 MB</span>
              <input
                ref={inputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
                className="sr-only"
                onChange={(e) => e.target.files?.[0] && start(e.target.files[0])}
              />
              {error && <span className="type-body-sm mt-2 text-error">{error}</span>}
            </label>
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
              <p className="type-body-md">Steps will appear here as the scan runs: Vision → Decisions → saved.</p>
            )}
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
              {(phase === 'working' || (phase === 'done' && !allShown)) && (
                <li className="flex items-center gap-3 rounded-2xl bg-white/50 p-3">
                  <span className="h-8 w-8 animate-pulse rounded-full bg-sage-100" />
                  <span className="type-body-md">{phase === 'working' ? PENDING_STEPS[pendingIdx] : 'Writing up…'}</span>
                </li>
              )}
            </ol>
          </GlassPanel>

          {allShown && item && (
            <GlassPanel radius="hero" className="animate-[fadeUp_.35s_ease-out] p-5">
              {editing ? (
                <EditForm item={item} onSave={saveEdit} onCancel={() => setEditing(false)} />
              ) : (
                <>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="type-micro mb-1 text-forest-mid">Saved to closet</p>
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

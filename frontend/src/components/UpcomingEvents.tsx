import { useEffect, useMemo, useState } from 'react';
import { IoCalendarOutline, IoLocationOutline, IoSparklesOutline } from 'react-icons/io5';
import { api } from '../lib/api';
import type { CalendarEvent, CalendarResponse } from '../lib/types';
import { GlassPanel } from './GlassPanel';

const DAYS_AHEAD = 14;
const COLLAPSED = 5;

function isoDay(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function time12(t: string | null) {
  if (!t) return null;
  const [h, m] = t.split(':').map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

function shortPlace(location: string) {
  // "K-ARI Chinatown, 3390 S State St #27, South Salt Lake, UT 84115" -> "K-ARI Chinatown · South Salt Lake"
  const parts = location.split(',').map((p) => p.trim()).filter(Boolean);
  if (parts.length <= 2) return parts.join(' · ');
  const city = parts.length >= 3 ? parts[parts.length - 2].replace(/\d+/g, '').trim() : '';
  return [parts[0], city].filter(Boolean).join(' · ');
}

/** The message the agent receives when you tap "Style it" on an event. */
export function styleMessage(e: CalendarEvent) {
  const d = new Date(e.date + 'T12:00:00');
  const when = d.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
  const t = time12(e.start_time);
  return (
    `Style me for "${e.name}" on ${when}${t ? ` at ${t}` : ''}` +
    (e.location ? ` at ${e.location}` : '') +
    '.' +
    (e.dress_code_hint ? ` Dress code: ${e.dress_code_hint}.` : '') +
    ' Pick the best outfit from my closet for this event and its weather.'
  );
}

export function UpcomingEvents({ onStyle, busy }: { onStyle: (e: CalendarEvent) => void; busy: string | null }) {
  const [cal, setCal] = useState<CalendarResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const start = new Date();
    const end = new Date(Date.now() + DAYS_AHEAD * 86_400_000);
    api.calendar(isoDay(start), isoDay(end)).then(setCal).catch(() => setFailed(true));
  }, []);

  const upcoming = useMemo(() => {
    if (!cal) return [];
    const now = new Date();
    const today = isoDay(now);
    const nowHm = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    // Hide events that already started earlier today.
    return cal.events.filter((e) => !(e.date === today && e.start_time && e.start_time < nowHm));
  }, [cal]);

  if (failed) return null;
  const shown = expanded ? upcoming : upcoming.slice(0, COLLAPSED);

  return (
    <GlassPanel radius="hero" className="mt-5 p-4 md:p-5">
      <div className="mb-3 flex items-end justify-between gap-3 px-1">
        <div>
          <p className="type-micro !text-white/75">Up next on your calendar</p>
          <p className="mt-0.5 text-[13px] text-white/70">
            {cal ? `${cal.label} · next ${DAYS_AHEAD} days` : 'Loading your calendar…'}
          </p>
        </div>
        <IoCalendarOutline className="text-white/70" size={20} />
      </div>

      {cal && upcoming.length === 0 && (
        <p className="px-1 pb-1 text-[14px] text-white/80">Nothing coming up. Describe your plans above instead.</p>
      )}

      <ul className="flex flex-col gap-2">
        {shown.map((e) => {
          const d = new Date(e.date + 'T12:00:00');
          const isBusy = busy === e.id;
          return (
            <li key={e.id} className="flex items-center gap-3 rounded-2xl bg-white/85 p-2.5 pr-3">
              <span className="flex w-14 shrink-0 flex-col items-center rounded-xl bg-sand-100 py-1.5">
                <span className="text-[9px] font-bold uppercase tracking-[1.5px] text-faint">
                  {d.toLocaleDateString(undefined, { weekday: 'short' })}
                </span>
                <span className="text-[17px] font-bold leading-5 text-ink">{d.getDate()}</span>
                <span className="text-[9px] font-semibold uppercase text-muted">
                  {d.toLocaleDateString(undefined, { month: 'short' })}
                </span>
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-x-2">
                  <span className="truncate text-[14px] font-semibold text-ink">{e.name}</span>
                  {e.calendar === 'demo' && (
                    <span className="rounded-full bg-sand-100 px-1.5 py-[1px] text-[9px] font-bold uppercase tracking-[1.2px] text-muted">
                      Demo
                    </span>
                  )}
                </span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[12px] text-muted">
                  <span>{time12(e.start_time) ?? 'All day'}</span>
                  {e.location && (
                    <span className="flex min-w-0 items-center gap-0.5 truncate">
                      <IoLocationOutline size={12} /> {shortPlace(e.location)}
                    </span>
                  )}
                  {e.dress_code_hint && <span className="capitalize">{e.dress_code_hint}</span>}
                </span>
              </span>
              <button
                type="button"
                onClick={() => onStyle(e)}
                disabled={busy !== null}
                className="flex shrink-0 items-center gap-1.5 rounded-full bg-forest px-3.5 py-2 text-[12px] font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-60"
              >
                <IoSparklesOutline size={14} />
                {isBusy ? 'Starting…' : 'Style it'}
              </button>
            </li>
          );
        })}
      </ul>

      {upcoming.length > COLLAPSED && (
        <button type="button" onClick={() => setExpanded(!expanded)} className="mt-3 px-1 text-[13px] font-semibold text-white/85 hover:text-white">
          {expanded ? 'Show fewer' : `Show all ${upcoming.length} events`}
        </button>
      )}
    </GlassPanel>
  );
}

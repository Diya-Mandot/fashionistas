import { IoRainyOutline, IoSunnyOutline, IoPartlySunnyOutline } from 'react-icons/io5';
import type { PlanDay } from '../lib/types';

function WeatherIcon({ pct }: { pct: number | null }) {
  if (pct != null && pct >= 50) return <IoRainyOutline size={15} />;
  if (pct != null && pct >= 25) return <IoPartlySunnyOutline size={15} />;
  return <IoSunnyOutline size={15} />;
}

export function DayTabs({ days, active, onChange }: { days: PlanDay[]; active: number; onChange: (n: number) => void }) {
  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" role="tablist">
      {days.map((d, n) => {
        const dt = new Date(d.date + 'T12:00:00');
        const on = n === active;
        return (
          <button
            key={d.date}
            role="tab"
            aria-selected={on}
            type="button"
            onClick={() => onChange(n)}
            className={`flex shrink-0 flex-col items-start rounded-2xl px-4 py-2.5 text-left transition ${
              on ? 'bg-forest text-white' : 'glass text-ink hover:bg-white/60'
            }`}
          >
            <span className={`text-[10px] font-bold uppercase tracking-[2px] ${on ? 'text-white/70' : 'text-faint'}`}>
              {dt.toLocaleDateString(undefined, { weekday: 'short' })}
            </span>
            <span className="text-[15px] font-bold">{dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
            {d.weather && (
              <span className={`mt-0.5 flex items-center gap-1 text-[11px] tabular-nums ${on ? 'text-white/85' : 'text-muted'}`}>
                <WeatherIcon pct={d.weather.precip_pct} />
                {d.weather.high_f != null && `${Math.round(d.weather.high_f)}°`}
                {d.weather.low_f != null && `/${Math.round(d.weather.low_f)}°`}
                {d.weather.precip_pct != null && ` · ${Math.round(d.weather.precip_pct)}%`}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

import { IoCloseOutline, IoLocationOutline, IoNavigateOutline } from 'react-icons/io5';
import type { DeviceLocation } from '../lib/types';

export function LocationChip({
  location,
  status,
  onLocate,
  onClear,
  dark,
}: {
  location: DeviceLocation | null;
  status: string;
  onLocate: () => void;
  onClear: () => void;
  dark: boolean;
}) {
  const base = `flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold ${
    dark ? 'bg-white/20 text-white' : 'bg-white/70 text-ink ring-1 ring-line'
  }`;
  if (location) {
    return (
      <span className={base} title="Used when your message doesn't name a city">
        <IoLocationOutline size={14} /> Near {location.label}
        <button type="button" onClick={onClear} aria-label="Stop using my location" className="ml-0.5 opacity-70 hover:opacity-100">
          <IoCloseOutline size={14} />
        </button>
      </span>
    );
  }
  return (
    <button type="button" onClick={onLocate} className={`${base} hover:opacity-90`} disabled={status === 'locating'}>
      <IoNavigateOutline size={13} />
      {status === 'locating' ? 'Locating…' : status === 'denied' ? 'Location blocked: allow it in the browser' : status === 'error' ? 'Couldn’t get location, retry' : 'Use my location'}
    </button>
  );
}

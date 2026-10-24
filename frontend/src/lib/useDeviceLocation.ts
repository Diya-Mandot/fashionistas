import { useCallback, useState } from 'react';
import { api } from './api';
import type { DeviceLocation } from './types';

const KEY = 'fashionistas.location';

function load(): DeviceLocation | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as DeviceLocation) : null;
  } catch {
    return null;
  }
}

/** Browser geolocation -> city (reverse-geocoded by the backend), remembered locally. */
export function useDeviceLocation() {
  const [location, setLocation] = useState<DeviceLocation | null>(load);
  const [status, setStatus] = useState<'idle' | 'locating' | 'denied' | 'error'>('idle');

  const locate = useCallback(() => {
    if (!('geolocation' in navigator)) {
      setStatus('error');
      return;
    }
    setStatus('locating');
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const place = await api.reverseGeocode(pos.coords.latitude, pos.coords.longitude);
          setLocation(place);
          localStorage.setItem(KEY, JSON.stringify(place));
          setStatus('idle');
        } catch {
          setStatus('error');
        }
      },
      (err) => setStatus(err.code === err.PERMISSION_DENIED ? 'denied' : 'error'),
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 30 * 60_000 },
    );
  }, []);

  const clear = useCallback(() => {
    localStorage.removeItem(KEY);
    setLocation(null);
  }, []);

  return { location, status, locate, clear };
}

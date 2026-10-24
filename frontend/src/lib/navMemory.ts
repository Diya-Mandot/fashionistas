import { useSyncExternalStore } from 'react';

/** Remembers where you last were inside the Stylist tab ("/" or "/?run=…"),
 *  so the nav's Stylist link brings you back to a running plan instead of resetting. */
let stylistPath = '/';
const listeners = new Set<() => void>();

export function setStylistPath(path: string) {
  if (path === stylistPath) return;
  stylistPath = path;
  listeners.forEach((l) => l());
}

export function useStylistPath() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => stylistPath,
  );
}

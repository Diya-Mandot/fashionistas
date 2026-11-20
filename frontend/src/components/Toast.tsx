import { useCallback, useEffect, useState } from 'react';

const SHOW_MS = 3200;

/** A short status message at the bottom of the screen. Render `toast` once; call `show(text)`. */
export function useToast() {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    if (!text) return;
    const t = setTimeout(() => setText(null), SHOW_MS);
    return () => clearTimeout(t);
  }, [text]);

  const toast = text ? (
    <div
      role="status"
      className="fixed inset-x-4 bottom-6 z-30 mx-auto w-fit max-w-[calc(100%-32px)] animate-[fadeUp_.25s_ease-out] rounded-full bg-forest px-5 py-3 text-center text-[13px] font-semibold text-white shadow-lg"
    >
      {text}
    </div>
  ) : null;

  return { toast, show: useCallback((t: string) => setText(t), []) };
}

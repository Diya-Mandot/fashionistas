import { useState } from 'react';

export function JsonBlock({ label, value }: { label: string; value: unknown }) {
  const [more, setMore] = useState(false);
  if (value === undefined || value === null) return null;
  const text = JSON.stringify(value, null, 2);
  const long = text.length > 700;
  return (
    <div>
      <p className="type-micro mb-1">{label}</p>
      <pre className="max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded-xl bg-[#FBFAF7] p-3 font-mono text-[11.5px] leading-[17px] text-ink ring-1 ring-line-subtle">
        {long && !more ? text.slice(0, 700) + '\n…' : text}
      </pre>
      {long && (
        <button type="button" onClick={() => setMore(!more)} className="mt-1 text-[12px] font-semibold text-ocean-deep">
          {more ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}

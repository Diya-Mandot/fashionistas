import { useState, type DragEvent } from 'react';
import { IoCloudUploadOutline } from 'react-icons/io5';

const ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif';

/** Drag-and-drop or click-to-upload area for one clothing photo. */
export function PhotoDrop({
  onFile,
  error,
  label = 'Drop a photo or click to upload',
}: {
  onFile: (file: File) => void;
  error?: string | null;
  label?: string;
}) {
  const [dragOver, setDragOver] = useState(false);
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  };
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={`flex aspect-[4/3] cursor-pointer flex-col items-center justify-center gap-3 rounded-card border-2 border-dashed px-4 text-center transition-colors lg:aspect-[5/6] ${
        dragOver ? 'border-emerald bg-[rgba(52,211,153,0.10)]' : 'border-sage-200 bg-white/60 hover:bg-white/80'
      }`}
    >
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-forest text-white">
        <IoCloudUploadOutline size={26} />
      </span>
      <span className="type-label-bold">{label}</span>
      <span className="type-body-sm">JPG, PNG, WEBP or HEIC · up to 15 MB</span>
      <input
        type="file"
        accept={ACCEPT}
        className="sr-only"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = ''; // let the same file be picked again
          if (f) onFile(f);
        }}
      />
      {error && <span className="type-body-sm mt-2 text-error">{error}</span>}
    </label>
  );
}

/** A local preview URL for formats the browser can show (not HEIC). */
export function previewUrl(file: File): string | null {
  return file.type.startsWith('image/') && !/heic|heif/i.test(file.type) ? URL.createObjectURL(file) : null;
}

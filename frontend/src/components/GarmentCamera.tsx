import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { IoCameraOutline } from 'react-icons/io5';

const MAX_PHOTO_SIDE = 1600;
const primary = 'inline-flex items-center justify-center gap-2 rounded-full bg-forest px-5 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50';
const secondary = 'rounded-full border border-line bg-white px-4 py-2.5 text-sm font-semibold text-ink hover:bg-sand-50';

type CameraView = 'closed' | 'opening' | 'live';

function cameraError(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError' || error.name === 'SecurityError') {
      return 'Allow camera access in your browser settings, or upload a photo.';
    }
    if (error.name === 'NotFoundError') return 'No camera was found. Connect a camera or upload a photo.';
    if (error.name === 'NotReadableError' || error.name === 'AbortError') {
      return 'The camera may be in use. Close other camera apps and try again, or upload a photo.';
    }
  }
  return 'The camera could not start. Try again or upload a photo.';
}

export function GarmentCamera({ children, onScan }: { children: ReactNode; onScan: (file: File) => void }) {
  const [view, setView] = useState<CameraView>('closed');
  const [ready, setReady] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const attempt = useRef(0);

  const stopCamera = useCallback(() => {
    attempt.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  useEffect(() => stopCamera, [stopCamera]);

  const closeCamera = () => {
    stopCamera();
    setView('closed');
    setCapturing(false);
  };

  const openCamera = async () => {
    setError(null);
    setReady(false);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Open this page over HTTPS or localhost to use the camera. You can also upload a photo.');
      setView('closed');
      return;
    }
    const current = ++attempt.current;
    setView('opening');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { width: { ideal: 1280 }, height: { ideal: 960 } },
      });
      if (current !== attempt.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      for (const track of stream.getVideoTracks()) {
        track.addEventListener('ended', () => {
          if (current !== attempt.current) return;
          stopCamera();
          setView('closed');
          setCapturing(false);
          setError('The camera disconnected. Try again or upload a photo.');
        }, { once: true });
      }
      setView('live');
    } catch (cause) {
      if (current !== attempt.current) return;
      setError(cameraError(cause));
      setView('closed');
    }
  };

  const attachVideo = useCallback((node: HTMLVideoElement | null) => {
    videoRef.current = node;
    if (node) node.srcObject = streamRef.current;
  }, []);

  const takePhoto = () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight || capturing) return;
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, MAX_PHOTO_SIDE / Math.max(video.videoWidth, video.videoHeight));
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) {
      setError('The browser could not capture a photo. Try again or upload a photo.');
      return;
    }
    const current = attempt.current;
    setCapturing(true);
    setError(null);
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (current !== attempt.current) return;
      setCapturing(false);
      if (!blob) {
        setError('The browser could not capture a photo. Try again or upload a photo.');
        return;
      }
      const file = new File([blob], 'garment-camera.jpg', { type: blob.type });
      stopCamera();
      onScan(file);
    }, 'image/jpeg', 0.9);
  };

  if (view === 'closed') {
    return (
      <div className="space-y-3">
        <button type="button" className={`${primary} w-full`} onClick={() => void openCamera()}>
          <IoCameraOutline size={18} aria-hidden="true" /> Use camera
        </button>
        {error && <p className="type-body-sm text-error" role="alert">{error}</p>}
        {children}
      </div>
    );
  }

  return (
    <section aria-label="Garment camera" className="space-y-3">
      <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded-card bg-sand-100">
        {view === 'opening' && <p className="type-body-sm px-4 text-center" role="status">Waiting for camera access…</p>}
        {view === 'live' && (
          <video
            ref={attachVideo}
            aria-label="Live camera preview"
            autoPlay
            muted
            playsInline
            onCanPlay={() => setReady(true)}
            className="h-full w-full bg-ink object-contain"
          />
        )}
      </div>
      {view === 'live' && <p className="type-body-sm">Hold one garment in frame. Keep its color and shape visible.</p>}
      {error && <p className="type-body-sm text-error" role="alert">{error}</p>}
      <div className="flex flex-wrap gap-2">
        {view === 'live' && (
          <button type="button" className={primary} disabled={!ready || capturing} onClick={takePhoto}>
            <IoCameraOutline size={18} aria-hidden="true" /> {capturing ? 'Capturing…' : 'Take photo and save'}
          </button>
        )}
        <button type="button" className={secondary} onClick={closeCamera}>Cancel</button>
      </div>
    </section>
  );
}

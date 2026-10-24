import { IoArrowBack } from 'react-icons/io5';
import { useNavigate } from 'react-router-dom';

/** Goes back within the app if there's somewhere to go back to, otherwise home. */
export function BackButton({ label = 'Back', to }: { label?: string; to?: string }) {
  const navigate = useNavigate();
  const go = () => {
    if (to) return navigate(to);
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
    if (idx > 0) navigate(-1);
    else navigate('/');
  };
  return (
    <button
      type="button"
      onClick={go}
      className="flex items-center gap-1.5 rounded-full bg-white/70 px-3.5 py-1.5 text-[13px] font-semibold text-ink ring-1 ring-line backdrop-blur hover:bg-white"
    >
      <IoArrowBack size={14} /> {label}
    </button>
  );
}

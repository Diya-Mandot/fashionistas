import type { IconType } from 'react-icons';
import {
  IoAlertCircleOutline,
  IoBagHandleOutline,
  IoCalendarOutline,
  IoCameraOutline,
  IoChatbubbleEllipsesOutline,
  IoCheckmarkCircleOutline,
  IoCloudUploadOutline,
  IoFlashOutline,
  IoGitBranchOutline,
  IoPartlySunnyOutline,
  IoPricetagsOutline,
  IoSearchOutline,
  IoShieldCheckmarkOutline,
  IoShirtOutline,
  IoSparklesOutline,
  IoStatsChartOutline,
} from 'react-icons/io5';
import type { TraceStep } from '../lib/types';

const BY_TOOL: Record<string, IconType> = {
  get_weather_forecast: IoPartlySunnyOutline,
  read_calendar: IoCalendarOutline,
  query_closet: IoShirtOutline,
  build_and_score_outfits: IoStatsChartOutline,
  find_closet_gaps: IoSearchOutline,
  suggest_secondhand_item: IoBagHandleOutline,
  upload: IoCloudUploadOutline,
  google_vision: IoCameraOutline,
  classify_item: IoPricetagsOutline,
  closet: IoCheckmarkCircleOutline,
};

const BY_KIND: Record<string, IconType> = {
  input: IoChatbubbleEllipsesOutline,
  thinking: IoSparklesOutline,
  decision: IoStatsChartOutline,
  validation: IoShieldCheckmarkOutline,
  fallback: IoGitBranchOutline,
  error: IoAlertCircleOutline,
  final: IoCheckmarkCircleOutline,
  message: IoFlashOutline,
};

export function StepIcon({ step, size = 16 }: { step: TraceStep; size?: number }) {
  const Icon = (step.tool && BY_TOOL[step.tool]) || BY_KIND[step.kind] || IoFlashOutline;
  const tone =
    step.kind === 'error'
      ? 'bg-error/10 text-error'
      : step.kind === 'fallback'
        ? 'bg-accent-light text-[#8A6236]'
        : step.kind === 'decision'
          ? 'bg-[rgba(52,211,153,0.16)] text-forest-mid'
          : 'bg-[rgba(91,141,184,0.14)] text-ocean-deep';
  return (
    <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${tone}`}>
      <Icon size={size} />
    </span>
  );
}

import { APP_NAME } from '../theme/brand';

export function Wordmark({ light = false, size = 28 }: { light?: boolean; size?: number }) {
  return (
    <span
      className={`font-logo font-bold tracking-tight ${light ? 'text-white' : 'text-forest'}`}
      style={{ fontSize: size, lineHeight: 1 }}
    >
      {APP_NAME}
    </span>
  );
}

import type { HTMLAttributes } from 'react';

type Props = HTMLAttributes<HTMLDivElement> & { radius?: 'card' | 'hero' };

export function GlassPanel({ radius = 'card', className = '', ...rest }: Props) {
  const r = radius === 'hero' ? 'rounded-hero' : 'rounded-card';
  return <div className={`glass ${r} ${className}`} {...rest} />;
}

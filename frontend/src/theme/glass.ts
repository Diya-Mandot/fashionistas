// Shared glassmorphism panel from ecostylistfe/theme/glass.ts (web branch).
// The CSS lives in the `.glass` class in src/index.css; this mirrors it for
// inline-style use.
import type { CSSProperties } from 'react';
import { colors } from './colors';

export const GLASS_PANEL: CSSProperties = {
  backgroundColor: colors.glassWeb,
  backdropFilter: 'blur(20px)',
  WebkitBackdropFilter: 'blur(20px)',
  border: `1px solid ${colors.glassBorder}`,
  boxShadow: '0 8px 28px rgba(20,50,40,0.14), inset 0 1px 0 rgba(255,255,255,0.5)',
};

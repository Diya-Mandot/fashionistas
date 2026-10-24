// Ported verbatim from ecostylistfe/theme/colors.ts. Do not invent new brand
// colors; derive shades from these.
export const colors = {
  background: '#FAF9F6', // Paper
  primary: '#1A3226', // Deep Forest
  accent: '#D4A373', // Warm Sand
  emerald: '#34D399', // Eco Emerald
  textDark: '#141414', // Primary Ink
  textMedium: '#6B6B6B',
  textLight: '#A0A0A0',
  white: '#FFFFFF',
  cardBg: '#FFFFFF',
  greenLight: '#EDF2EF',
  accentLight: '#FAF3EA',
  border: '#EBEBEB',
  borderSubtle: '#F0EDE8',
  error: '#B42318',

  // Ocean blue accent, sprinkled alongside the primary green. oceanDeep keeps
  // 4.5:1 contrast for text/icons on light glass.
  ocean: '#5B8DB8',
  oceanDeep: '#3E6E8E',

  glassWeb: 'rgba(255,255,255,0.30)',
  glassBorder: 'rgba(255,255,255,0.48)',
  glassGreenTint: 'rgba(52,211,153,0.16)',
  glassBlueTint: 'rgba(91,141,184,0.16)',

  // Warm neutrals used across capstone screens for chips and dividers.
  sand50: '#FBFAF7',
  sand100: '#F7F2EA',
  sand200: '#E6DFD2',
  sage100: '#E7F0EA',
  sage200: '#C8D9CE',
  forestMid: '#2F6B3B',
} as const;

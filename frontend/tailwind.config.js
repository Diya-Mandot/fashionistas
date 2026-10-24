import { colors } from './src/theme/colors.ts';

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: colors.background,
        forest: colors.primary,
        sand: colors.accent,
        emerald: colors.emerald,
        ink: colors.textDark,
        muted: colors.textMedium,
        faint: colors.textLight,
        'green-light': colors.greenLight,
        'accent-light': colors.accentLight,
        line: colors.border,
        'line-subtle': colors.borderSubtle,
        error: colors.error,
        ocean: colors.ocean,
        'ocean-deep': colors.oceanDeep,
        'sand-50': colors.sand50,
        'sand-100': colors.sand100,
        'sand-200': colors.sand200,
        'sage-100': colors.sage100,
        'sage-200': colors.sage200,
        'forest-mid': colors.forestMid,
      },
      fontFamily: {
        display: ['Syne', 'sans-serif'],
        sans: ['Manrope', 'system-ui', 'sans-serif'],
        logo: ['"Playfair Display"', 'serif'],
      },
      borderRadius: {
        card: '20px',
        hero: '24px',
      },
    },
  },
  plugins: [],
};

import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        j: {
          sky: '#00d2ff',
          deep: '#1a6fa8',
          navy: '#0a2b45',
          mid: '#0d3a6b',
          accent: '#7ddcff',
          glow: 'rgba(0,210,255,0.15)',
          gold: '#f5c842',
          dark: '#020406',
          bg: '#020406',
          surface: '#0f1e2d',
          'surface-hover': '#121f2e',
          border: 'rgba(0,210,255,0.1)',
          text: '#e8f4ff',
          'text-dim': 'rgba(180,210,240,0.68)',
        },
      },
      fontFamily: {
        sans: ['Outfit', 'system-ui', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
        display: ['Bebas Neue', 'sans-serif'],
      },
      borderRadius: {
        sm: '2px',
        md: '4px',
        lg: '6px',
      },
    },
  },
  plugins: [],
};

export default config;

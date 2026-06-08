'use client';
import { create } from 'zustand';

export type ThemeId = 'sky' | 'phantom' | 'arctic' | 'ember';

export interface ThemeState {
  theme: ThemeId;
  font: 'sans' | 'mono' | 'display';
  customVars: Record<string, string>;
  setTheme: (t: ThemeId) => void;
  setFont: (f: 'sans' | 'mono' | 'display') => void;
  setCustomVar: (key: string, val: string) => void;
  resetCustomVars: () => void;
}

function getInitialTheme(): ThemeId {
  if (typeof window === 'undefined') return 'sky';
  return (localStorage.getItem('j-theme') as ThemeId) || 'sky';
}

function getInitialFont(): 'sans' | 'mono' | 'display' {
  if (typeof window === 'undefined') return 'sans';
  return (localStorage.getItem('j-font') as 'sans' | 'mono' | 'display') || 'sans';
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: getInitialTheme(),
  font: getInitialFont(),
  customVars: {},
  setTheme: (t) => {
    localStorage.setItem('j-theme', t);
    set({ theme: t });
  },
  setFont: (f) => {
    localStorage.setItem('j-font', f);
    set({ font: f });
  },
  setCustomVar: (key, val) =>
    set((s) => ({ customVars: { ...s.customVars, [key]: val } })),
  resetCustomVars: () => set({ customVars: {} }),
}));

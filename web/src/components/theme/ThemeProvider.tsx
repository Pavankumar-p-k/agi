'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { useThemeStore } from '@/stores/themeStore';

const FONT_MAP = {
  sans: 'var(--j-font-sans)',
  mono: 'var(--j-font-mono)',
  display: 'var(--j-font-display)',
};

export default function ThemeProvider({ children }: { children: ReactNode }) {
  const { theme, font, customVars } = useThemeStore();
  const appliedCustomKeys = useRef<Set<string>>(new Set());

  useEffect(() => {
    document.documentElement.className = `theme-${theme}`;
  }, [theme]);

  useEffect(() => {
    document.documentElement.style.setProperty('--j-font-active', FONT_MAP[font]);
  }, [font]);

  useEffect(() => {
    appliedCustomKeys.current.forEach((key) => {
      if (!(key in customVars)) document.documentElement.style.removeProperty(key);
    });
    appliedCustomKeys.current = new Set(Object.keys(customVars));
    Object.entries(customVars).forEach(([key, val]) => {
      document.documentElement.style.setProperty(key, val);
    });
  }, [customVars]);

  return <>{children}</>;
}

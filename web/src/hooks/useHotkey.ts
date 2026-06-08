'use client';

import { useEffect, useCallback } from 'react';

type HotkeyHandler = (e: KeyboardEvent) => void;

interface HotkeyDef {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
  handler: HotkeyHandler;
  enabled?: boolean;
}

const SHORTCUTS: { keys: string; label: string; desc: string }[] = [
  { keys: '⌘K', label: 'Cmd+K', desc: 'Command palette' },
  { keys: '⌘N', label: 'Cmd+N', desc: 'New chat' },
  { keys: '⌘,', label: 'Cmd+,', desc: 'Settings' },
  { keys: '⌘⇧M', label: 'Cmd+Shift+M', desc: 'Monitor' },
  { keys: '⌘⇧L', label: 'Cmd+Shift+L', desc: 'Log viewer' },
  { keys: '⌘B', label: 'Cmd+B', desc: 'Backend panel' },
  { keys: '⌘⇧T', label: 'Cmd+Shift+T', desc: 'Theme studio' },
];

export { SHORTCUTS };

export function useHotkey(def: HotkeyDef) {
  const enabled = def.enabled !== false;

  const handler = useCallback((e: KeyboardEvent) => {
    if (e.repeat) return;
    const target = e.target as HTMLElement;
    const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;

    // Allow Cmd/Ctrl shortcuts even in inputs, but block single-key shortcuts there
    if (isInput && !def.ctrl && !def.meta) return;

    const matchKey = e.key.toLowerCase() === def.key.toLowerCase();
    const matchCtrl = def.ctrl ? e.ctrlKey : !e.ctrlKey;
    const matchMeta = def.meta ? e.metaKey : !e.metaKey;
    const matchShift = def.shift ? e.shiftKey : !e.shiftKey;
    const matchAlt = def.alt ? e.altKey : !e.altKey;

    if (matchKey && matchCtrl && matchMeta && matchShift && matchAlt) {
      e.preventDefault();
      def.handler(e);
    }
  }, [def.key, def.ctrl, def.meta, def.shift, def.alt, def.handler]);

  useEffect(() => {
    if (!enabled) return;
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handler, enabled]);
}

export function useHotkeys(shortcuts: HotkeyDef[]) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      for (const def of shortcuts) {
        if (def.enabled === false) continue;
        if (e.repeat) continue;
        const target = e.target as HTMLElement;
        const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
        if (isInput && !def.ctrl && !def.meta) continue;

        const matchKey = e.key.toLowerCase() === def.key.toLowerCase();
        const matchCtrl = def.ctrl ? e.ctrlKey : !e.ctrlKey;
        const matchMeta = def.meta ? e.metaKey : !e.metaKey;
        const matchShift = def.shift ? e.shiftKey : !e.shiftKey;
        const matchAlt = def.alt ? e.altKey : !e.altKey;

        if (matchKey && matchCtrl && matchMeta && matchShift && matchAlt) {
          e.preventDefault();
          def.handler(e);
          return;
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [shortcuts]);
}

import type { ReactNode } from 'react';

export default function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block text-[10px] font-mono px-3 py-1 border border-[rgba(var(--j-sky-rgb),0.24)] text-[var(--j-sky)] bg-[rgba(var(--j-sky-rgb),0.06)] tracking-[0.14em] uppercase">
      {children}
    </span>
  );
}

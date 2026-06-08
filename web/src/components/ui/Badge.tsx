import type { ReactNode } from 'react';

interface Props {
  variant?: 'default' | 'new' | 'hot' | 'core';
  children: ReactNode;
}

const variants: Record<string, string> = {
  default: 'bg-[rgba(var(--j-sky-rgb),0.08)] text-[var(--j-sky)] border-[rgba(var(--j-sky-rgb),0.22)]',
  new: 'bg-[rgba(var(--j-sky-rgb),0.14)] text-[var(--j-sky)] border-[rgba(var(--j-sky-rgb),0.36)]',
  hot: 'bg-[rgba(var(--j-gold-rgb),0.1)] text-[var(--j-gold)] border-[rgba(var(--j-gold-rgb),0.32)]',
  core: 'bg-[rgba(124,58,237,0.12)] text-[#a78bfa] border-[rgba(124,58,237,0.32)]',
};

export default function Badge({ variant = 'default', children }: Props) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[10px] font-mono uppercase tracking-[0.12em] border ${variants[variant]}`}>
      {children}
    </span>
  );
}

'use client';

import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  children: ReactNode;
}

const base = 'clip-hud inline-flex items-center justify-center gap-2 font-medium transition-all duration-200 cursor-pointer border uppercase tracking-[0.16em] font-mono';

const variants: Record<string, string> = {
  primary: 'bg-[var(--j-sky)] text-[var(--j-dark)] border-transparent shadow-[0_0_30px_rgba(var(--j-sky-rgb),0.28)] hover:bg-[var(--j-text)] hover:-translate-y-0.5 hover:shadow-[0_0_46px_rgba(var(--j-sky-rgb),0.44)]',
  ghost: 'bg-transparent text-[var(--j-text-dim)] border-[var(--j-border-bright)] hover:border-[var(--j-sky)] hover:text-[var(--j-sky)] hover:bg-[rgba(var(--j-sky-rgb),0.06)] hover:-translate-y-0.5',
  danger: 'bg-transparent text-[#ff4757] border-[rgba(255,71,87,0.3)] hover:bg-[rgba(255,71,87,0.1)] hover:-translate-y-0.5',
};

const sizes: Record<string, string> = {
  sm: 'px-3 py-1.5 text-[10px]',
  md: 'px-5 py-2.5 text-xs',
};

export default function Button({ variant = 'ghost', size = 'md', className = '', children, ...props }: Props) {
  return (
    <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props}>
      {children}
    </button>
  );
}

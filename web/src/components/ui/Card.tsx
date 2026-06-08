'use client';

import { motion } from 'framer-motion';
import type { ReactNode, HTMLAttributes } from 'react';

interface Props extends HTMLAttributes<HTMLDivElement> {
  accent?: boolean;
  variant?: 'default' | 'sky' | 'deep';
  children: ReactNode;
}

const accentMap: Record<string, string> = {
  default: '',
  sky: 'before:bg-[var(--j-sky)]',
  deep: 'before:bg-[var(--j-gold)]',
};

export default function Card({ accent = false, variant = accent ? 'sky' : 'default', className = '', children, ...props }: Props) {
  return (
    <motion.div
      whileHover={{ y: -4, borderColor: 'var(--j-border-bright)' }}
      whileTap={{ scale: 0.995 }}
      transition={{ duration: 0.2 }}
      className={`group relative overflow-hidden bg-[var(--j-surface)] border border-[var(--j-border)] rounded-[var(--j-radius-lg)] p-4 cursor-pointer transition-colors duration-300 hover:bg-[var(--j-surface-hover)] before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:opacity-0 before:shadow-[0_0_12px_currentColor] before:transition-opacity hover:before:opacity-100 after:absolute after:inset-x-0 after:top-0 after:h-px after:origin-center after:scale-x-0 after:bg-gradient-to-r after:from-transparent after:via-[var(--j-sky)] after:to-transparent after:transition-transform after:duration-300 hover:after:scale-x-100 ${accentMap[variant]} ${className}`}
      {...(props as React.ComponentProps<typeof motion.div>)}
    >
      <div className="relative z-[1]">{children}</div>
    </motion.div>
  );
}

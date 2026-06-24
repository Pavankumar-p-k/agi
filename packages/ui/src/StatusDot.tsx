'use client';

import type { CSSProperties } from 'react';

const STATUS_COLORS: Record<string, string> = {
  PENDING: '#8b8b8b',
  RUNNING: '#00d2ff',
  COMPLETED: '#22c55e',
  FAILED: '#ef4444',
  SUSPENDED: '#f5c842',
  CANCELLED: '#6b7280',
};

interface Props {
  status: string;
  size?: number;
  pulse?: boolean;
  style?: CSSProperties;
}

export function StatusDot({ status, size = 10, pulse, style }: Props) {
  const color = STATUS_COLORS[status] || STATUS_COLORS.PENDING;
  return (
    <span
      className={pulse ? 'animate-pulse' : ''}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: '50%',
        backgroundColor: color,
        boxShadow: `0 0 6px ${color}44`,
        flexShrink: 0,
        ...style,
      }}
    />
  );
}

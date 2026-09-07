'use client';

interface Props {
  value: number;
  max?: number;
  height?: number;
  color?: string;
  label?: string;
}

export function ProgressBar({ value, max = 100, height = 6, color, label }: Props) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
      <div
        style={{
          flex: 1,
          height,
          borderRadius: 3,
          backgroundColor: 'rgba(255,255,255,0.08)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            borderRadius: 3,
            backgroundColor: color || 'var(--j-sky, #00d2ff)',
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      {label !== undefined && (
        <span style={{ fontSize: 11, color: 'var(--j-text-dim, rgba(180,210,240,0.68))', minWidth: 32, textAlign: 'right' }}>
          {label}
        </span>
      )}
    </div>
  );
}
